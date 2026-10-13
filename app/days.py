from datetime import date

from flask import Blueprint, render_template, request

from app.db import db
from app.models import Exercise, PlanDay, PlannedItem
from app.parsing import parse_reps, parse_sets, parse_weight

bp = Blueprint("days", __name__)


def parse_day(iso_date: str) -> date | None:
    try:
        return date.fromisoformat(iso_date)
    except ValueError:
        return None


def get_or_create_plan_day(day: date) -> PlanDay:
    plan_day = PlanDay.query.filter_by(date=day).one_or_none()
    if plan_day is None:
        plan_day = PlanDay(date=day, kind="train")
        db.session.add(plan_day)
        db.session.flush()
    return plan_day


def get_or_create_exercise(name: str) -> Exercise:
    exercise = Exercise.query.filter_by(name=name).one_or_none()
    if exercise is None:
        exercise = Exercise(name=name)
        db.session.add(exercise)
        db.session.flush()
    return exercise


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


@bp.post("/day/<iso_date>/plan")
def add_plan_item(iso_date: str):
    day = parse_day(iso_date)
    if day is None:
        return "无效日期", 400
    name = (request.form.get("exercise") or "").strip()
    if name:
        plan_day = get_or_create_plan_day(day)
        db.session.add(
            PlannedItem(
                plan_day=plan_day,
                exercise=get_or_create_exercise(name),
                weight_kg=parse_weight(request.form.get("weight")),
                sets=parse_sets(request.form.get("sets")),
                reps=parse_reps(request.form.get("reps")),
                position=len(plan_day.items),
            )
        )
        db.session.commit()
    return render_day_fragment(day)


@bp.post("/plan-item/<int:item_id>/delete")
def delete_plan_item(item_id: int):
    item = db.session.get(PlannedItem, item_id)
    if item is None:
        return "找不到这条", 404
    day = item.plan_day.date
    db.session.delete(item)
    db.session.commit()
    return render_day_fragment(day)


@bp.post("/plan-item/<int:item_id>/move")
def move_plan_item(item_id: int):
    item = db.session.get(PlannedItem, item_id)
    if item is None:
        return "找不到这条", 404
    day = item.plan_day.date
    siblings = list(item.plan_day.items)
    index = siblings.index(item)
    target = index - 1 if request.form.get("direction") == "up" else index + 1
    if 0 <= target < len(siblings):
        siblings[index], siblings[target] = siblings[target], siblings[index]
        for position, sibling in enumerate(siblings):
            sibling.position = position
        db.session.commit()
    return render_day_fragment(day)
