"""归属隔离：唯一允许判断「属不属于当前用户」的地方（HLD §8；SRS FR-3.1、FR-3.2、FR-3.4）。

硬不变量（AGENTS.md 1）：判断只发生在 service 层。routers 不得自行拼 `user_id` 过滤条件，
只把当前用户的 id 传进来。三种查法：

- `select_owned()`：列表 / 聚合查询的基座，把范围收窄到 `user_id`；
- `require_*()`：按 id 取资源。**父链每一层都校验** `user_id`（例如
  `template_item → template_day → template`）——只信子表上冗余的 `user_id` 会漏掉
  父子链不一致的脏行，而那正是「A 的条目挂到 B 的模板下」这类越权的形状；
- `find_*()`：按业务键取资源，不存在返回 `None`（GET /days 允许「当天还没有计划日」）。

DayNote 没有 id 级 helper 是故意的：它 1:1 挂在 PlanDay 上，入口恒为 `PUT /days/{iso}/note`，
归属经由计划日的 (user_id, date) 校验（HLD §8.3 的「note」一行即此）。

失败一律 `NotFoundError`：不存在 / 不属于你 / 父子链不一致三者不可区分（HLD §9.2），
文案与状态码由 `app/core/errors.py` 一处产出。
"""

from __future__ import annotations

from datetime import date
from typing import TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import (
    ActualItem,
    BodyMetric,
    CycleTemplate,
    Exercise,
    PlanDay,
    PlannedItem,
    TemplateDay,
    TemplateItem,
    UserScoped,
)

OwnedT = TypeVar("OwnedT", bound=UserScoped)
RowT = TypeVar("RowT")


def select_owned(model: type[OwnedT], user_id: int) -> Select[OwnedT]:
    """列表查询的唯一基座：`WHERE model.user_id = :user_id`。"""
    return select(model).where(model.user_id == user_id)


def _require(db: Session, stmt: Select[RowT]) -> RowT:
    """`require_*` 的共用出口：查不到就是 404，不存在第二种失败形态。"""
    found = db.scalar(stmt)
    if found is None:
        raise NotFoundError
    return found


# ---------- 按业务键（不存在是正常结果） ----------


def find_plan_day(db: Session, *, user_id: int, day: date) -> PlanDay | None:
    """按 (user_id, date) 定位计划日（SRS FR-5：一天最多一个）。"""
    return db.scalar(select_owned(PlanDay, user_id).where(PlanDay.date == day))


def find_exercise(db: Session, *, user_id: int, name: str) -> Exercise | None:
    """动作库按用户命名空间查找（SRS FR-3.4）：A 的「深蹲」对 B 是另一个动作。"""
    return db.scalar(select_owned(Exercise, user_id).where(Exercise.name == name))


def find_body_metric(db: Session, *, user_id: int, week_start: date) -> BodyMetric | None:
    """按 (user_id, 周起点) 取周体重；没有记录是正常状态（SRS FR-10）。"""
    return db.scalar(select_owned(BodyMetric, user_id).where(BodyMetric.week_start == week_start))


# ---------- 按 id（属不属于你都必须不可区分） ----------


def require_planned_item(db: Session, *, user_id: int, planned_item_id: int) -> PlannedItem:
    """计划条目 → 计划日父链校验（删除、上下移）。"""
    return _require(
        db,
        select(PlannedItem)
        .join(PlanDay, PlannedItem.plan_day_id == PlanDay.id)
        .where(
            PlannedItem.id == planned_item_id,
            PlannedItem.user_id == user_id,
            PlanDay.user_id == user_id,
        ),
    )


def require_actual_item(db: Session, *, user_id: int, actual_item_id: int) -> ActualItem:
    """实际条目 → 计划日父链校验（PATCH autosave、删除）。"""
    return _require(
        db,
        select(ActualItem)
        .join(PlanDay, ActualItem.plan_day_id == PlanDay.id)
        .where(
            ActualItem.id == actual_item_id,
            ActualItem.user_id == user_id,
            PlanDay.user_id == user_id,
        ),
    )


def require_template(db: Session, *, user_id: int, template_id: int) -> CycleTemplate:
    """模板本身即根资源（删除、铺开）。"""
    return _require(
        db,
        select(CycleTemplate).where(
            CycleTemplate.id == template_id,
            CycleTemplate.user_id == user_id,
        ),
    )


def require_template_day(db: Session, *, user_id: int, template_day_id: int) -> TemplateDay:
    """模板日 → 模板父链校验。"""
    return _require(
        db,
        select(TemplateDay)
        .join(CycleTemplate, TemplateDay.template_id == CycleTemplate.id)
        .where(
            TemplateDay.id == template_day_id,
            TemplateDay.user_id == user_id,
            CycleTemplate.user_id == user_id,
        ),
    )


def require_template_item(db: Session, *, user_id: int, template_item_id: int) -> TemplateItem:
    """模板条目 → 模板日 → 模板，两层父链都校验。"""
    return _require(
        db,
        select(TemplateItem)
        .join(TemplateDay, TemplateItem.template_day_id == TemplateDay.id)
        .join(CycleTemplate, TemplateDay.template_id == CycleTemplate.id)
        .where(
            TemplateItem.id == template_item_id,
            TemplateItem.user_id == user_id,
            TemplateDay.user_id == user_id,
            CycleTemplate.user_id == user_id,
        ),
    )
