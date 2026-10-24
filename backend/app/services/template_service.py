"""循环模板 CRUD 与 apply 逐日铺排（SRS FR-9、HLD §9.1/§5.2；v1 `app/cycle.py` 语义照搬）。

四条业务规则（全部来自 FR-9.2 与 v1，逐条都有测试钉住）：

- **名称**：`strip()` 后为空 → `"未命名循环"`（不报错，不落空串）。
- **天数**：`parse_sets(length_days) or 8` 再夹到 `1..12` —— 非法/缺省回退 **8**，超界**静默截断
  12**。`parse_sets` 只认 `>0` 整数，于是 `"abc"` / `"0"` / `"-3"` / `"8.5"` 全部落到回退 8
  （v1 同义）。
- **逐日**：`kind` 只取 `train`/`rest`，**非 `"rest"` 一律 `train`**（不 422、不报错）；`title`
  strip 后为空 → NULL。
- **条目**：只有动作名（模板不含重量，FR-9.2）；**strip 后为空的行忽略**（v1 的「忽略空行」），
  `position` 从 0 递增；`sets`/`reps` 恒 NULL —— 那两列是 v1 遗留，v2 一个字节都不写。

`days` 数组按**下标**对应 `day_index`：多出来的天被忽略（v1 只读 `range(length)` 内的表单字段），
不足的补默认训练日（`train` / 无标题 / 无条目）。天数永远等于夹过的 `length_days`，骨架不缺行。

**apply 的判定是「该日期是否已有 PlanDay」，不是「是否已填内容」**，且查的是**当前用户**的
`(user_id, date)`（模型唯一键）：已有就**跳过且一个字节都不改**（FR-9.3「绝不覆盖」），并把它记入
`skipped_dates` 回给前端。因此这里**不能**复用 `days_service.get_or_create_plan_day()` —— 那是
「没有就建」，apply 要「有就跳过」，两者语义相反（票 14 注释）。

复制到计划日的只有骨架字段（exercise / sets / reps / position，HLD §5.2）：`weight_kg` 恒 NULL
（模板不含重量），`sets`/`reps` 从模板抄过来也恒 NULL；注释与标题以外的实际记录不碰。

隔离：`require_template()` 出 404（跨用户 apply / 删除同码同文案），逐日与条目查询全部经
`select_owned()` 收窄，且**每一层都带 `user_id`**（脏行对双方都不可见，与 `isolation.py`
同一取向）。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import cast

from sqlalchemy.orm import Session

from app.models import CycleTemplate, Exercise, PlanDay, PlannedItem, TemplateDay, TemplateItem
from app.parsing import parse_sets
from app.schemas import (
    DayKind,
    TemplateAggregate,
    TemplateApplyResult,
    TemplateCreate,
    TemplateDayIn,
    TemplateDayOut,
    TemplateItemOut,
)
from app.services.days_service import get_or_create_exercise
from app.services.isolation import find_plan_day, require_template, select_owned

DEFAULT_TEMPLATE_NAME = "未命名循环"
DEFAULT_LENGTH_DAYS = 8
MIN_TEMPLATE_DAYS = 1
MAX_TEMPLATE_DAYS = 12

TRAIN_KIND = "train"
REST_KIND = "rest"


# ---------- 读 ----------


def list_templates(db: Session, *, user_id: int) -> list[TemplateAggregate]:
    """当前用户的全部模板 + 逐日骨架 + 条目（FR-9.1），按模板 id 升序（v1 同序）。"""
    templates = list(db.scalars(select_owned(CycleTemplate, user_id).order_by(CycleTemplate.id)))
    return _aggregates(db, user_id=user_id, templates=templates)


# ---------- 写 ----------


def create_template(db: Session, *, user_id: int, payload: TemplateCreate) -> TemplateAggregate:
    """建模板 + 逐日骨架（FR-9.2）：名称/天数归一、kind 归一、空动作名忽略、条目自动入动作库。"""
    template = CycleTemplate(
        user_id=user_id,
        name=_name(payload.name),
        length_days=_length(payload.length_days),
    )
    db.add(template)
    for day_index in range(template.length_days):
        source = payload.days[day_index] if day_index < len(payload.days) else None
        template_day = TemplateDay(
            user_id=user_id,
            day_index=day_index,
            kind=_kind(source),
            title=_title(source),
            template=template,
        )
        db.add(template_day)
        for position, exercise in enumerate(_exercises(source)):
            db.add(
                TemplateItem(
                    user_id=user_id,
                    # 模板条目不含重量；sets/reps 是 v1 遗留列，v2 恒写 NULL（FR-9.2）
                    exercise_id=get_or_create_exercise(db, user_id=user_id, name=exercise).id,
                    sets=None,
                    reps=None,
                    position=position,
                    template_day=template_day,
                )
            )
    db.commit()
    return _aggregate(db, user_id=user_id, template=template)


def delete_template(db: Session, *, user_id: int, template_id: int) -> list[TemplateAggregate]:
    """删除模板（FR-9.4）：级联天与条目（ORM cascade + FK ON DELETE CASCADE），返回剩余列表。"""
    template = require_template(db, user_id=user_id, template_id=template_id)
    db.delete(template)
    db.commit()
    return list_templates(db, user_id=user_id)


def apply_template(
    db: Session, *, user_id: int, template_id: int, start: date
) -> TemplateApplyResult:
    """按 `day_index` 从 `start` 逐日铺排（FR-9.3）：已有 PlanDay 的日期**跳过且绝不覆盖**。

    跳过与新建的计数、以及被跳过的日期一起回给前端（v1 只回一个中文句子，v2 结构化）；
    `skipped_dates` 天然升序（按 `day_index` 递增铺排）。跨用户模板由 `require_template` 出 404。
    """
    template = require_template(db, user_id=user_id, template_id=template_id)
    days = _days_by_template(db, user_id=user_id, template_ids=[template.id])[template.id]
    items = _items_by_day(db, user_id=user_id, template_day_ids=[day.id for day in days])

    created = 0
    skipped_dates: list[date] = []
    for template_day in days:
        target = start + timedelta(days=template_day.day_index)
        # 「有就跳过」与「没有就建」是两条相反的语义：这里刻意不用 get_or_create_plan_day
        if find_plan_day(db, user_id=user_id, day=target) is not None:
            skipped_dates.append(target)
            continue
        plan_day = PlanDay(
            user_id=user_id,
            date=target,
            kind=template_day.kind,
            title=template_day.title,
        )
        db.add(plan_day)
        for item, _exercise in items[template_day.id]:
            db.add(
                PlannedItem(
                    user_id=user_id,
                    plan_day=plan_day,
                    exercise_id=item.exercise_id,
                    # 模板不含重量；sets/reps 模板侧恒 NULL，抄过来也恒 NULL
                    # （HLD §5.2 的骨架四字段）
                    weight_kg=None,
                    sets=item.sets,
                    reps=item.reps,
                    position=item.position,
                )
            )
        created += 1
    db.commit()
    return TemplateApplyResult(
        created=created, skipped=len(skipped_dates), skipped_dates=skipped_dates
    )


# ---------- 归一规则（FR-9.2，v1 `app/cycle.py` 同义）----------


def _name(raw: str | None) -> str:
    """空名不报错：strip 后为空就落到默认名（FR-9.2）。"""
    return (raw or "").strip() or DEFAULT_TEMPLATE_NAME


def _length(raw: str | None) -> int:
    """`parse_sets` 只认 >0 整数，其余（含非法文本）回退 8，再夹到 1..12（超界静默截断）。"""
    parsed = parse_sets(raw) or DEFAULT_LENGTH_DAYS
    return max(MIN_TEMPLATE_DAYS, min(parsed, MAX_TEMPLATE_DAYS))


def _kind(source: TemplateDayIn | None) -> str:
    """只有精确的 `rest` 是休息日，其余（含缺省与脏值）一律训练日。"""
    return REST_KIND if source is not None and source.kind == REST_KIND else TRAIN_KIND


def _title(source: TemplateDayIn | None) -> str | None:
    """标题 strip 后为空即无标题（NULL），不留空串。"""
    if source is None:
        return None
    return (source.title or "").strip() or None


def _exercises(source: TemplateDayIn | None) -> list[str]:
    """当天的动作名：strip 后为空的行忽略（v1「忽略空行」），其余按输入顺序。"""
    if source is None:
        return []
    names = [item.exercise.strip() for item in source.items]
    return [name for name in names if name]


# ---------- 内部：聚合组装与逐层收窄查询 ----------


def _aggregate(db: Session, *, user_id: int, template: CycleTemplate) -> TemplateAggregate:
    """单个模板的骨架（create 的返回值）；与列表共用同一条组装路径，避免两处形状漂移。"""
    return _aggregates(db, user_id=user_id, templates=[template])[0]


def _aggregates(
    db: Session, *, user_id: int, templates: Sequence[CycleTemplate]
) -> list[TemplateAggregate]:
    """批量组装：3 条查询（模板已给、天、条目）而不是每个模板每天各查一次。"""
    if not templates:
        return []
    days = _days_by_template(db, user_id=user_id, template_ids=[t.id for t in templates])
    items = _items_by_day(
        db,
        user_id=user_id,
        template_day_ids=[day.id for group in days.values() for day in group],
    )
    return [
        TemplateAggregate(
            id=template.id,
            name=template.name,
            length_days=template.length_days,
            days=[
                TemplateDayOut(
                    day_index=day.day_index,
                    kind=cast(DayKind, day.kind),
                    title=day.title,
                    items=[
                        TemplateItemOut(exercise=exercise, position=item.position)
                        for item, exercise in items[day.id]
                    ],
                )
                for day in days[template.id]
            ],
        )
        for template in templates
    ]


def _days_by_template(
    db: Session, *, user_id: int, template_ids: Sequence[int]
) -> dict[int, list[TemplateDay]]:
    """按模板分组的天，`day_index` 升序（apply 的铺排顺序与列表展示顺序同源）。"""
    grouped: dict[int, list[TemplateDay]] = {template_id: [] for template_id in template_ids}
    if not template_ids:
        return grouped
    for day in db.scalars(
        select_owned(TemplateDay, user_id)
        .where(TemplateDay.template_id.in_(template_ids))
        .order_by(TemplateDay.day_index, TemplateDay.id)
    ):
        grouped[day.template_id].append(day)
    return grouped


def _items_by_day(
    db: Session, *, user_id: int, template_day_ids: Sequence[int]
) -> dict[int, list[tuple[TemplateItem, str]]]:
    """按天分组的 `(条目, 动作名)`，`position` 升序。

    join 上的 `Exercise.user_id` 也收窄：条目指向别人动作库的脏行对**双方**都不可见，
    与 `days_service._planned_items` 同一取向（否则 apply 会把脏行的 exercise_id 抄进本人计划日）。
    """
    grouped: dict[int, list[tuple[TemplateItem, str]]] = {
        template_day_id: [] for template_day_id in template_day_ids
    }
    if not template_day_ids:
        return grouped
    rows = db.execute(
        select_owned(TemplateItem, user_id)
        .add_columns(Exercise.name)
        .join(Exercise, TemplateItem.exercise_id == Exercise.id)
        .where(
            TemplateItem.template_day_id.in_(template_day_ids),
            Exercise.user_id == user_id,
        )
        .order_by(TemplateItem.position, TemplateItem.id)
    )
    for item, exercise in rows:
        grouped[item.template_day_id].append((item, exercise))
    return grouped
