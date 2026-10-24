"""月历聚合读（SRS FR-4、HLD §9.1）。

语义与 v1 `app/calendar.py` 一致（D9：照搬，不重新设计）：
- `month_grid`：`[None] * first.weekday()` 前补、尾部补到 7 的整数倍，再切片成周；
- `parse_month`：`date.fromisoformat(f"{raw}-01")` 失败或缺失 → 回退当月，服务端不报错（FR-4.2）；
- `logged_dates` = 有实际条目的日期集合（不是「有计划日」的日期）；
- 周行 = `week_start`（该周第一个非空日期的周一，可能落在上一个月）+ 该周 BodyMetric。

隔离：PlanDay / ActualItem / BodyMetric 三处查询全部经 `select_owned` 收窄（硬不变量 1）；
`logged_dates` 的 join 查询同样带 `user_id`，否则 A 的日历会显示 B 的记录日（票 10 易漏点）。
"""

from __future__ import annotations

import calendar as _calendar
from datetime import date, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActualItem, BodyMetric, PlanDay
from app.parsing import parse_day
from app.schemas import BodyMetricOut, CalendarAggregate, CalendarCell, CalendarWeek, DayKind
from app.services.isolation import select_owned


def month_grid(year: int, month: int) -> list[list[date | None]]:
    """把一个月切成整周（周一为一周起点），月初日前与月末日后补 None。"""
    first = date(year, month, 1)
    days_in_month = _calendar.monthrange(year, month)[1]
    cells: list[date | None] = [None] * first.weekday()
    cells.extend(date(year, month, d) for d in range(1, days_in_month + 1))
    while len(cells) % 7:
        cells.append(None)
    return [cells[i : i + 7] for i in range(0, len(cells), 7)]


def parse_month(raw: str | None) -> tuple[int, int]:
    """解析 ?month=YYYY-MM；缺省或格式不对时回退到当月（服务端不报错，FR-4.2）。

    「认不出」的判定挂在 `parsing.parse_day`（硬不变量 2：parsing 不抛错，日期解析也只有一处）；
    这里只负责**回退语义**，与 days 的「非法 → 400」刻意不共用。
    """
    parsed = parse_day(f"{raw}-01") if raw else None
    if parsed is not None:
        return parsed.year, parsed.month
    today = date.today()
    return today.year, today.month


def week_start_for(day: date) -> date:
    """这个日期所在那一周的周一（周起点的唯一算法，SRS FR-10 同用）。"""
    return day - timedelta(days=day.weekday())


def metric_out(metric: BodyMetric) -> BodyMetricOut:
    """BodyMetric 行 → 契约形状（月历周行与票 15 的 upsert 返回值共用这一份映射）。"""
    return BodyMetricOut(
        week_start=metric.week_start,
        weight_kg=metric.weight_kg,
        body_fat_pct=metric.body_fat_pct,
        note=metric.note,
    )


def calendar_month(db: Session, *, user_id: int, month: str | None) -> CalendarAggregate:
    """组装月历聚合；`month` 非法或缺失时静默回退当月。"""
    year, month_num = parse_month(month)
    grid = month_grid(year, month_num)
    month_start = date(year, month_num, 1)
    month_end = month_start.replace(day=_calendar.monthrange(year, month_num)[1])

    plan_days = {
        p.date: p
        for p in db.scalars(
            select_owned(PlanDay, user_id).where(
                PlanDay.date >= month_start, PlanDay.date <= month_end
            )
        )
    }
    # logged_dates：join 必须同样带 user_id 收窄，与 select_owned 一个形状
    logged_rows = db.execute(
        select(PlanDay.date)
        .join(ActualItem, ActualItem.plan_day_id == PlanDay.id)
        .where(
            PlanDay.user_id == user_id,
            ActualItem.user_id == user_id,
            PlanDay.date >= month_start,
            PlanDay.date <= month_end,
        )
        .distinct()
    )
    logged_dates = sorted(day for (day,) in logged_rows.all())

    week_starts: list[date] = []
    for week in grid:
        first_day = next((d for d in week if d is not None), None)
        assert first_day is not None  # 网格按周切片，每行必有真实日期
        week_starts.append(week_start_for(first_day))

    metrics = {
        m.week_start: m
        for m in db.scalars(
            select_owned(BodyMetric, user_id).where(BodyMetric.week_start.in_(week_starts))
        )
    }

    weeks: list[CalendarWeek] = []
    for week, week_start in zip(grid, week_starts, strict=True):
        cells: list[CalendarCell | None] = []
        for d in week:
            if d is None:
                cells.append(None)
                continue
            plan_day = plan_days.get(d)
            cells.append(
                CalendarCell(
                    date=d,
                    # ORM 列是 str，取值域只有 train/rest（models 默认 train）
                    kind=None if plan_day is None else cast(DayKind, plan_day.kind),
                    title=None if plan_day is None else plan_day.title,
                )
            )
        metric = metrics.get(week_start)
        weeks.append(
            CalendarWeek(
                week_start=week_start,
                cells=cells,
                metric=None if metric is None else metric_out(metric),
            )
        )

    return CalendarAggregate(year=year, month=month_num, weeks=weeks, logged_dates=logged_dates)
