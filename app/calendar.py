import calendar as _calendar
from datetime import date

from flask import Blueprint, render_template, request

from app.db import db
from app.models import ActualItem, PlanDay

bp = Blueprint("calendar", __name__)

WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]


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
    """解析 ?month=YYYY-MM；缺省或格式不对时回退到当月。"""
    if raw:
        try:
            parsed = date.fromisoformat(f"{raw}-01")
        except ValueError:
            pass
        else:
            return parsed.year, parsed.month
    today = date.today()
    return today.year, today.month


def shift_month(year: int, month: int, delta: int) -> str:
    index = year * 12 + (month - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


@bp.get("/")
def index():
    year, month = parse_month(request.args.get("month"))
    weeks = month_grid(year, month)
    days = [d for w in weeks for d in w if d]

    plan_days = {
        p.date: p
        for p in PlanDay.query.filter(
            PlanDay.date >= days[0], PlanDay.date <= days[-1]
        ).all()
    }
    logged_dates = {
        day
        for (day,) in db.session.query(PlanDay.date)
        .join(ActualItem, ActualItem.plan_day_id == PlanDay.id)
        .filter(PlanDay.date >= days[0], PlanDay.date <= days[-1])
        .distinct()
    }

    return render_template(
        "calendar.html",
        year=year,
        month=month,
        weeks=weeks,
        weekdays=WEEKDAY_NAMES,
        plan_days=plan_days,
        logged_dates=logged_dates,
        today=date.today(),
        prev_month=shift_month(year, month, -1),
        next_month=shift_month(year, month, 1),
    )
