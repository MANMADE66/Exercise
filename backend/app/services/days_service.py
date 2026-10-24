"""日聚合读写：计划条目增删移 + 实际条目（含 prefill）+ 计划日惰性创建
（SRS FR-5、FR-6、FR-7、FR-8.2；HLD §9.1、§9.2）。

三条读/建约定：

- `aggregate_day()` **无副作用**：没有 PlanDay 的日期返回空结构（`kind`/`title` 为 None、
  三个集合为空、`note` 为空串），**不落库**（FR-5.2）。这与 v1 相反 —— v1 在读路径上也
  会走到 `get_or_create_plan_day`，v2 的 GET 必须不写库。
- `get_or_create_plan_day()` **只在写路径上**用（票 11/12/14 复用，票 13 还要判「文本非空
  才建」）：默认 `kind="train"`、`title=None`，与 v1 `app/days.py:19` 一致。只 `flush()`
  不 `commit()` —— 事务由调用方一并收尾，避免写操作出现半个事务。

计划条目三个写操作（FR-6）与实际条目四个写操作（FR-7）全部复用同一收尾：`commit()` 之后调
`aggregate_day()` 返回**新鲜日聚合**（D7），前端整体替换状态、不再补发 GET。

实际条目的两条特殊语义：

- `prefill_actual_items()` 是**幂等**的（FR-7.1）：只补「还没有对应实际条目」的计划条目，
  重复调用不产生重复；当天没有 PlanDay 时静默 no-op（不隐式建日 —— 没计划就无可复制）。
- `update_actual_item()` 是**三态**的（FR-7.2）：字段缺省不动、显式 `null` 置空、空串置空。
  三者都表现为 `None` 值，只能看 `ActualItemUpdate.model_fields_set`；用 `exclude_none` 或
  「值是 None 就跳过」的一把梭会静默丢掉「置空」这一态。

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
from app.schemas import (
    ActualItemOut,
    ActualItemUpdate,
    DayAggregate,
    DayKind,
    MoveDirection,
    PlannedItemOut,
)
from app.services.isolation import (
    find_exercise,
    find_plan_day,
    require_actual_item,
    require_planned_item,
    select_owned,
)

DEFAULT_KIND = "train"

RowT = TypeVar("RowT")

# 两张带 `position` 的子表共用同一套重排（删除后不留空洞，见 `_renumber`）。
PositionedT = TypeVar("PositionedT", PlannedItem, ActualItem)


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


# ---------- 实际条目写操作（FR-7，全部返回新鲜日聚合）----------


def prefill_actual_items(db: Session, *, user_id: int, day: date) -> DayAggregate:
    """按计划预填（FR-7.1）：给每个尚无实际条目的计划条目复制一条，重复调用幂等。

    当天没有 PlanDay 时静默 no-op（不隐式建日）：prefill 的语义是「照计划复制」，没计划就
    没有可复制的东西（票 12 裁定，与 v1 `app/days.py:prefill_actual` 一致）。
    """
    plan_day = find_plan_day(db, user_id=user_id, day=day)
    if plan_day is not None:
        try:
            with db.begin_nested():
                _copy_missing_actuals(db, user_id=user_id, plan_day=plan_day)
        except IntegrityError:
            # 并发 prefill 撞 UNIQUE(plan_day_id, planned_item_id)：整批回滚后重算一次
            # （重算走真实查询就能看见对方刚建的条目，于是什么也不补）。重算仍撞就抛出，
            # 不吞脏数据 —— 与 `_insert_or_refetch` 同一取向，只是粒度是整批而非单条。
            with db.begin_nested():
                _copy_missing_actuals(db, user_id=user_id, plan_day=plan_day)
        db.commit()
    return aggregate_day(db, user_id=user_id, day=day)


def add_actual_item(
    db: Session,
    *,
    user_id: int,
    day: date,
    exercise: str,
    weight: str | None = None,
    sets: str | None = None,
    reps: str | None = None,
    note: str | None = None,
) -> DayAggregate:
    """新增计划外条目（FR-7.3）：`planned_item_id` 为 NULL，置于当天末位；隐式建日同计划条目。"""
    plan_day = get_or_create_plan_day(db, user_id=user_id, day=day)
    db.add(
        ActualItem(
            user_id=user_id,
            plan_day_id=plan_day.id,
            planned_item_id=None,
            exercise_id=get_or_create_exercise(db, user_id=user_id, name=exercise).id,
            weight_kg=parse_weight(weight),
            sets=parse_sets(sets),
            # 次数是自由文本，空即空串（同计划条目 / v1）；备注 trim 后为空则视为未填
            reps=parse_reps(reps),
            note=_parse_note(note),
            position=len(_actual_siblings(db, user_id=user_id, plan_day_id=plan_day.id)),
        )
    )
    db.commit()
    return aggregate_day(db, user_id=user_id, day=day)


def update_actual_item(
    db: Session, *, user_id: int, actual_item_id: int, changes: ActualItemUpdate
) -> DayAggregate:
    """行内更新（FR-7.2）：只动 `changes.model_fields_set` 里的字段，逐字段三态。

    - 字段缺席 → 这一列一个字节都不碰（不能先 `model_dump()` 再赋值：缺席值也是 `None`）；
    - 显式 `null` / 空串 → 该列置空（`weight_kg`/`sets`/`note` 落 NULL，`reps` 落空串）。
    """
    item = require_actual_item(db, user_id=user_id, actual_item_id=actual_item_id)
    day = item.plan_day.date
    for field in changes.model_fields_set:
        column, parse = _ACTUAL_FIELD_UPDATES[field]
        setattr(item, column, parse(getattr(changes, field)))
    db.commit()
    return aggregate_day(db, user_id=user_id, day=day)


def delete_actual_item(db: Session, *, user_id: int, actual_item_id: int) -> DayAggregate:
    """删除实际条目（FR-7.4）：直接删；删完把剩余 position 重排回 0..n-1。

    重排理由与计划条目相同（票 11 裁定 ③）：新增用 `position = len(actuals)`，留着空洞会让
    下一条添加撞号，两个约束（末尾追加 + position 连续）只能靠删完重排同时成立。
    """
    item = require_actual_item(db, user_id=user_id, actual_item_id=actual_item_id)
    day = item.plan_day.date
    plan_day_id = item.plan_day_id
    db.delete(item)
    db.flush()
    _renumber(_actual_siblings(db, user_id=user_id, plan_day_id=plan_day_id))
    db.commit()
    return aggregate_day(db, user_id=user_id, day=day)


# ---------- 内部 ----------


def _copy_missing_actuals(db: Session, *, user_id: int, plan_day: PlanDay) -> None:
    """prefill 的一次完整复制（复制**当前计划值**，不是模板）：只补缺的，position 顺末尾递增。"""
    already = _linked_planned_item_ids(db, user_id=user_id, plan_day_id=plan_day.id)
    # 同一次请求内的多条沿用一个递增值：在循环里重算 len(actuals) 会让它们全挤在同一 position
    next_position = len(_actual_siblings(db, user_id=user_id, plan_day_id=plan_day.id))
    for planned_item in _siblings(db, user_id=user_id, plan_day_id=plan_day.id):
        if planned_item.id in already:
            continue
        db.add(
            ActualItem(
                user_id=user_id,
                plan_day_id=plan_day.id,
                planned_item_id=planned_item.id,
                exercise_id=planned_item.exercise_id,
                weight_kg=planned_item.weight_kg,
                sets=planned_item.sets,
                reps=planned_item.reps,
                note=None,
                position=next_position,
            )
        )
        next_position += 1


def _linked_planned_item_ids(db: Session, *, user_id: int, plan_day_id: int) -> set[int]:
    """当天已经「有实际条目」的计划条目 id 集合 —— prefill 幂等的唯一依据。"""
    rows = db.scalars(
        select_owned(ActualItem, user_id).where(
            ActualItem.plan_day_id == plan_day_id,
            ActualItem.planned_item_id.is_not(None),
        )
    )
    return {row.planned_item_id for row in rows if row.planned_item_id is not None}


def _actual_siblings(db: Session, *, user_id: int, plan_day_id: int) -> list[ActualItem]:
    """同一天的实际条目，按 (position, id) 升序 —— 与聚合的排序口径一致。"""
    return list(
        db.scalars(
            select_owned(ActualItem, user_id)
            .where(ActualItem.plan_day_id == plan_day_id)
            .order_by(ActualItem.position, ActualItem.id)
        )
    )


def _parse_note(raw: str | None) -> str | None:
    """备注：trim 后为空即视为未填（v1 `(note or "").strip() or None` 同义）。"""
    return None if raw is None else raw.strip() or None


# 契约字段名 → (列名, 解析器)。**必须显式写列名**：`weight` 在契约里叫 `weight`、列却叫
# `weight_kg`，直接 `setattr(item, field, ...)` 会静默写到一个非映射的 Python 属性上 ——
# 不报错、不落库、响应里照旧回旧值（sets/reps/note 恰好同名，于是只有 weight 静默失效）。
# 空串 / None 一律落到「置空」侧（FR-7.2）。表里查不到字段名会 KeyError：可更新字段已由契约
# 限死在四个，不认识的 key 是 bug，宁可炸出来也不静默略过。
_ACTUAL_FIELD_UPDATES: dict[str, tuple[str, Callable[[str | None], str | int | float | None]]] = {
    "weight": ("weight_kg", parse_weight),
    "sets": ("sets", parse_sets),
    "reps": ("reps", parse_reps),
    "note": ("note", _parse_note),
}


def _siblings(db: Session, *, user_id: int, plan_day_id: int) -> list[PlannedItem]:
    """同一天的兄弟条目，按 (position, id) 升序 —— 与聚合的排序口径一致。"""
    return list(
        db.scalars(
            select_owned(PlannedItem, user_id)
            .where(PlannedItem.plan_day_id == plan_day_id)
            .order_by(PlannedItem.position, PlannedItem.id)
        )
    )


def _renumber(siblings: Sequence[PositionedT]) -> None:
    """按给定顺序把 position 重排为 0..n-1（计划条目与实际条目共用）。

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
