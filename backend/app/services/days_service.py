"""日聚合读写：计划条目增删移 + 计划日惰性创建（SRS FR-5、FR-6、FR-8.2；HLD §9.1、§9.2）。

三条读/建约定：

- `aggregate_day()` **无副作用**：没有 PlanDay 的日期返回空结构（`kind`/`title` 为 None、
  三个集合为空、`note` 为空串），**不落库**（FR-5.2）。这与 v1 相反 —— v1 在读路径上也
  会走到 `get_or_create_plan_day`，v2 的 GET 必须不写库。
- `get_or_create_plan_day()` **只在写路径上**用（票 11/12/14 复用，票 13 还要判「文本非空
  才建」）：默认 `kind="train"`、`title=None`，与 v1 `app/days.py:19` 一致。只 `flush()`
  不 `commit()` —— 事务由调用方一并收尾，避免写操作出现半个事务。

计划条目三个写操作（FR-6）全部复用同一收尾：`commit()` 之后调 `aggregate_day()` 返回
**新鲜日聚合**（D7），前端整体替换状态、不再补发 GET。

聚合与兄弟条目查询全部经 `services/isolation.py` 的 `select_owned()` 收窄（硬不变量 1），
routers 只把 `user_id` 传进来，不碰过滤条件；按 id 取资源走 `require_*()`（404 只由那一处产出）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import TypeVar, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ActualItem, DayNote, Exercise, PlanDay, PlannedItem
from app.parsing import parse_reps, parse_sets, parse_weight
from app.schemas import ActualItemOut, DayAggregate, DayKind, MoveDirection, PlannedItemOut
from app.services.isolation import (
    find_exercise,
    find_plan_day,
    require_planned_item,
    select_owned,
)

DEFAULT_KIND = "train"

RowT = TypeVar("RowT")


def aggregate_day(db: Session, *, user_id: int, day: date) -> DayAggregate:
    """当天聚合（FR-5.1）：只读，缺 PlanDay 时返回空结构，绝不隐式建日（FR-5.2）。"""
    plan_day = find_plan_day(db, user_id=user_id, day=day)
    if plan_day is None:
        return DayAggregate(
            date=day,
            kind=None,
            title=None,
            planned_items=[],
            actual_items=[],
            note="",
        )
    return DayAggregate(
        date=plan_day.date,
        kind=cast(DayKind, plan_day.kind),
        title=plan_day.title,
        planned_items=_planned_items(db, user_id=user_id, plan_day_id=plan_day.id),
        actual_items=_actual_items(db, user_id=user_id, plan_day_id=plan_day.id),
        note=_note_text(db, user_id=user_id, plan_day_id=plan_day.id),
    )


def get_or_create_plan_day(db: Session, *, user_id: int, day: date) -> PlanDay:
    """写路径专用：取当天计划日，没有就建一条默认训练日（v1 语义，不覆盖已有 kind/title）。

    隐式建日在这条路径上合法（写条目必须有 PlanDay）：`kind` 一律 `train`、`title` 为 NULL，
    与 FR-8.2 的「笔记文本非空才建日」是两条独立规则（那条在票 13 的 note 路径上判）。
    """
    existing = find_plan_day(db, user_id=user_id, day=day)
    if existing is not None:
        return existing
    plan_day = PlanDay(user_id=user_id, date=day, kind=DEFAULT_KIND, title=None)
    return _insert_or_refetch(db, plan_day, lambda: find_plan_day(db, user_id=user_id, day=day))


def get_or_create_exercise(db: Session, *, user_id: int, name: str) -> Exercise:
    """动作名 → 本人的动作库行（FR-3.4、FR-6.1）：只在本人命名空间里查，没有才建。"""
    existing = find_exercise(db, user_id=user_id, name=name)
    if existing is not None:
        return existing
    exercise = Exercise(user_id=user_id, name=name)
    return _insert_or_refetch(db, exercise, lambda: find_exercise(db, user_id=user_id, name=name))


# ---------- 计划条目写操作（FR-6，全部返回新鲜日聚合）----------


def add_planned_item(
    db: Session,
    *,
    user_id: int,
    day: date,
    exercise: str,
    weight: str | None = None,
    sets: str | None = None,
    reps: str | None = None,
) -> DayAggregate:
    """添加计划条目（FR-6.1、FR-6.4）：动作自动入本人动作库、容错解析、置于末位。"""
    plan_day = get_or_create_plan_day(db, user_id=user_id, day=day)
    db.add(
        PlannedItem(
            user_id=user_id,
            plan_day_id=plan_day.id,
            exercise_id=get_or_create_exercise(db, user_id=user_id, name=exercise).id,
            weight_kg=parse_weight(weight),
            sets=parse_sets(sets),
            # 次数是自由文本，解析只 trim；v1 同样原样落库（空即空串，不是 NULL）
            reps=parse_reps(reps),
            position=len(_siblings(db, user_id=user_id, plan_day_id=plan_day.id)),
        )
    )
    db.commit()
    return aggregate_day(db, user_id=user_id, day=day)


def delete_planned_item(db: Session, *, user_id: int, planned_item_id: int) -> DayAggregate:
    """删除计划条目（FR-6.2）：关联实际条目不受影响，其 `planned_item_id` 由外键置空。"""
    item = require_planned_item(db, user_id=user_id, planned_item_id=planned_item_id)
    day = item.plan_day.date
    plan_day_id = item.plan_day_id
    db.delete(item)
    db.flush()
    # 删完把剩余条目重排回 0..n-1：留着空洞会让下一次添加的 `position = len(items)` 撞号
    _renumber(_siblings(db, user_id=user_id, plan_day_id=plan_day_id))
    db.commit()
    return aggregate_day(db, user_id=user_id, day=day)


def move_planned_item(
    db: Session, *, user_id: int, planned_item_id: int, direction: MoveDirection
) -> DayAggregate:
    """上下移动（FR-6.3）：交换后**全组重排** position；已在边界时静默成功（不改任何行）。"""
    item = require_planned_item(db, user_id=user_id, planned_item_id=planned_item_id)
    day = item.plan_day.date
    siblings = _siblings(db, user_id=user_id, plan_day_id=item.plan_day_id)
    index = next(position for position, sibling in enumerate(siblings) if sibling.id == item.id)
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(siblings):
        siblings[index], siblings[target] = siblings[target], siblings[index]
        _renumber(siblings)
    db.commit()
    return aggregate_day(db, user_id=user_id, day=day)


# ---------- 内部 ----------


def _siblings(db: Session, *, user_id: int, plan_day_id: int) -> list[PlannedItem]:
    """同一天的兄弟条目，按 (position, id) 升序 —— 与聚合的排序口径一致。"""
    return list(
        db.scalars(
            select_owned(PlannedItem, user_id)
            .where(PlannedItem.plan_day_id == plan_day_id)
            .order_by(PlannedItem.position, PlannedItem.id)
        )
    )


def _renumber(siblings: Sequence[PlannedItem]) -> None:
    """按给定顺序把 position 重排为 0..n-1。

    全组重排，而不是只交换两个值：v1 遗留库里可能有重复 position（并列插入），
    只换值会让重复继续存在，后续排序就退化成「看 id 猜」的不稳定顺序。
    """
    for position, sibling in enumerate(siblings):
        sibling.position = position


def _insert_or_refetch(
    db: Session,
    row: RowT,
    refetch: Callable[[], RowT | None],
) -> RowT:
    """在 SAVEPOINT 里插入；撞唯一键（并发 get-or-create）就只回滚这一条，再重查复用。

    - 不用 `db.rollback()`：调用方在同一事务里可能已经 flush 了计划日等前置行，整事务回滚
      会把它们一起丢掉 —— 保存点只丢失败的这一条（票 09 留下的 `IntegrityError` 欠账）。
    - 重查也查不到说明撞的不是本 helper 假设的那个唯一键（数据脏了），直接抛出，不吞。
    """
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        found = refetch()
        if found is None:
            raise
        return found
    return row


def _planned_items(db: Session, *, user_id: int, plan_day_id: int) -> list[PlannedItemOut]:
    """计划条目按 `position` 升序（同 position 再按 id，保证顺序稳定）。"""
    rows = db.execute(
        select_owned(PlannedItem, user_id)
        .add_columns(Exercise.name)
        .join(Exercise, PlannedItem.exercise_id == Exercise.id)
        .where(
            PlannedItem.plan_day_id == plan_day_id,
            # 脏行（条目指向别人动作库）对双方都不可见，与 isolation.require_* 同一取向
            Exercise.user_id == user_id,
        )
        .order_by(PlannedItem.position, PlannedItem.id)
    )
    return [
        PlannedItemOut(
            id=item.id,
            exercise=exercise,
            weight_kg=item.weight_kg,
            sets=item.sets,
            reps=item.reps,
            position=item.position,
        )
        for item, exercise in rows
    ]


def _actual_items(db: Session, *, user_id: int, plan_day_id: int) -> list[ActualItemOut]:
    """实际条目按 `position` 升序；`planned_item_id` 供前端对齐预填来源。"""
    rows = db.execute(
        select_owned(ActualItem, user_id)
        .add_columns(Exercise.name)
        .join(Exercise, ActualItem.exercise_id == Exercise.id)
        .where(
            ActualItem.plan_day_id == plan_day_id,
            Exercise.user_id == user_id,
        )
        .order_by(ActualItem.position, ActualItem.id)
    )
    return [
        ActualItemOut(
            id=item.id,
            planned_item_id=item.planned_item_id,
            exercise=exercise,
            weight_kg=item.weight_kg,
            sets=item.sets,
            reps=item.reps,
            note=item.note,
            position=item.position,
        )
        for item, exercise in rows
    ]


def _note_text(db: Session, *, user_id: int, plan_day_id: int) -> str:
    """感受笔记 1:1 挂计划日；没有记录即空串（前端永远拿到字符串，不用判 null）。"""
    found = db.scalar(select_owned(DayNote, user_id).where(DayNote.plan_day_id == plan_day_id))
    return "" if found is None else found.text
