from datetime import date

from flask import Blueprint, render_template

from app.models import PlanDay

bp = Blueprint("days", __name__)


def format_weight(value: float) -> str:
    return f"{value:g}"


def format_dose(weight_kg, sets, reps) -> str:
    """把重量 / 组数 / 次数拼成一行可读的剂量；空值一律跳过，不显示 None。"""
    parts = []
    if weight_kg is not None:
        parts.append(f"{format_weight(weight_kg)} kg")
    if sets is not None:
        parts.append(f"{sets} 组")
    if reps:
        parts.append(str(reps))
    return " · ".join(parts)


def render_day_fragment(day: date) -> str:
    """渲染某一天的详情片段；Day 5/6/7 复用这个函数。"""
    plan_day = PlanDay.query.filter_by(date=day).one_or_none()
    return render_template(
        "_day_detail.html",
        day=day,
        plan_day=plan_day,
        planned=list(plan_day.items) if plan_day else [],
        actuals=list(plan_day.actuals) if plan_day else [],
        dose=format_dose,
    )


@bp.get("/day/<iso_date>")
def day_detail(iso_date: str):
    try:
        day = date.fromisoformat(iso_date)
    except ValueError:
        return "无效日期", 400
    return render_day_fragment(day)
