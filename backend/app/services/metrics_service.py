"""周体重 upsert（SRS FR-10、HLD §9.1）。

语义与 v1 `app/metrics.py:save_metric` 一致（D9：照搬，不重新设计）：

- `week_start` **在服务端归一**：路径参数收的是「该周任意一天」，`week_start_for()` 算出这一周的
  周一再 upsert。传周三也落到该周周一那一行 —— v1 没有「必须周一，否则 400」的约束（票 15 裁定，
  本票不顺手加）。键恒为周一，与 `body_metric` 的 `UNIQUE(user_id, week_start)` 对齐；
- `weight` 非法（`parse_weight` 给 None）→ **不落库** + 422（FR-10.2）。这一关挡在契约层
  `BodyMetricUpdate.weight` 的 validator 上，请求根本进不到 handler，库自然零变化；这里再解析一次
  只为把文本变成数值（类型收窄），不产生第二条错误路径；
- `body_fat` 走同一解析但**不报错**：可选字段，认不出就是 NULL（v1 同样静默）；
- `note` strip 后为空即 NULL；
- PUT 是**整体替换**：没传的 `body_fat` / `note` 一律写成 NULL（与 v1 `metric.body_fat_pct =
  parse_weight(...)` 一致），不是「缺省不动」。

隔离：定位走 `find_body_metric`（按 `(user_id, 周起点)`，票 08 已建），新行 `user_id` 取当前用户。
A 与 B 可以各有同一周的行，B 的 PUT 绝不会改到 A 的那一行（票 15 易漏点）。

读路径（月历周行里的周体重）仍在 `calendar_service.py`；`week_start_for` 与 BodyMetric → 契约的
映射也从那里取，周起点的算法与形状各只有一份。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import BodyMetric
from app.parsing import parse_weight
from app.schemas import BodyMetricOut
from app.services.calendar_service import metric_out, week_start_for
from app.services.isolation import find_body_metric


def upsert_week_metric(
    db: Session,
    *,
    user_id: int,
    day: date,
    weight: str,
    body_fat: str | None = None,
    note: str | None = None,
) -> BodyMetricOut:
    """把 `day` 所在那一周的体重写成 `weight`（FR-10.1），返回该周 metric。"""
    week_start = week_start_for(day)
    weight_kg = _weight_kg(weight)
    body_fat_pct = parse_weight(body_fat)
    note_text = (note or "").strip() or None

    metric = find_body_metric(db, user_id=user_id, week_start=week_start)
    if metric is None:
        metric = _insert_week_metric(
            db,
            user_id=user_id,
            week_start=week_start,
            weight_kg=weight_kg,
            body_fat_pct=body_fat_pct,
            note=note_text,
        )
    # 新插的行与「撞键后重查到的行」都要写一遍：并发同周 PUT 时后到的照样覆盖（upsert 语义）
    metric.weight_kg = weight_kg
    metric.body_fat_pct = body_fat_pct
    metric.note = note_text
    db.commit()
    return metric_out(metric)


def _weight_kg(raw: str) -> float:
    """体重的数值形态。非法值在契约层已 422 拦掉，这里只为收窄类型（FR-10.2 不走第二条路径）。"""
    parsed = parse_weight(raw)
    assert parsed is not None
    return parsed


def _insert_week_metric(
    db: Session,
    *,
    user_id: int,
    week_start: date,
    weight_kg: float,
    body_fat_pct: float | None,
    note: str | None,
) -> BodyMetric:
    """插一行周体重；并发同周 PUT 撞唯一键时只回滚这一条，重查复用。

    用 SAVEPOINT 而不用 `db.rollback()`：调用方事务里可能已有别的待提交行，整事务回滚会把它们
    一起丢掉（与 `days_service._insert_or_refetch` 同一取向）。重查也查不到说明撞的不是本 helper
    假设的那个唯一键（数据脏了），直接抛出，不吞。
    """
    metric = BodyMetric(
        user_id=user_id,
        week_start=week_start,
        weight_kg=weight_kg,
        body_fat_pct=body_fat_pct,
        note=note,
    )
    try:
        with db.begin_nested():
            db.add(metric)
            db.flush()
    except IntegrityError:
        found = find_body_metric(db, user_id=user_id, week_start=week_start)
        if found is None:
            raise
        return found
    return metric
