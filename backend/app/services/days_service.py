"""日聚合读与计划日惰性创建（SRS FR-5、FR-8.2；HLD §9.1、§9.2）。

两条读/建约定：

- `aggregate_day()` **无副作用**：没有 PlanDay 的日期返回空结构（`kind`/`title` 为 None、
  三个集合为空、`note` 为空串），**不落库**（FR-5.2）。这与 v1 相反 —— v1 在读路径上也
  会走到 `get_or_create_plan_day`，v2 的 GET 必须不写库。
- `get_or_create_plan_day()` **只在写路径上**用（票 11/12/14 复用，票 13 还要判「文本非空
  才建」）：默认 `kind="train"`、`title=None`，与 v1 `app/days.py:19` 一致。只 `flush()`
  不 `commit()` —— 事务由调用方一并收尾，避免写操作出现半个事务。

聚合里的三组查询全部经 `services/isolation.py` 的 `select_owned()` 收窄（硬不变量 1），
routers 只把 `user_id` 传进来，不碰过滤条件。
"""

from __future__ import annotations

from datetime import date
from typing import cast

from sqlalchemy.orm import Session

from app.models import ActualItem, DayNote, Exercise, PlanDay, PlannedItem
from app.schemas import ActualItemOut, DayAggregate, DayKind, PlannedItemOut
from app.services.isolation import find_plan_day, select_owned

DEFAULT_KIND = "train"


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
    """写路径专用：取当天计划日，没有就建一条默认训练日（v1 语义，不覆盖已有 kind/title）。"""
    existing = find_plan_day(db, user_id=user_id, day=day)
    if existing is not None:
        return existing
    plan_day = PlanDay(user_id=user_id, date=day, kind=DEFAULT_KIND, title=None)
    db.add(plan_day)
    db.flush()
    return plan_day


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
