from datetime import date, timedelta

from flask import Blueprint, redirect, render_template, request, url_for

from app.db import db
from app.models import (
    CycleTemplate,
    Exercise,
    PlanDay,
    PlannedItem,
    TemplateDay,
    TemplateItem,
)
from app.parsing import parse_sets

bp = Blueprint("cycle", __name__)

MAX_TEMPLATE_DAYS = 12


def apply_template(template_id: int, start: date) -> tuple[int, int]:
    """把模板从 start 起逐日铺到日历上；已有计划的日期跳过，绝不覆盖。"""
    template = db.session.get(CycleTemplate, template_id)
    if template is None:
        raise ValueError(f"template {template_id} not found")

    created = 0
    skipped = 0
    for template_day in template.days:
        target = start + timedelta(days=template_day.day_index)
        if PlanDay.query.filter_by(date=target).one_or_none() is not None:
            skipped += 1
            continue
        plan_day = PlanDay(date=target, kind=template_day.kind, title=template_day.title)
        db.session.add(plan_day)
        db.session.flush()
        for item in template_day.items:
            db.session.add(
                PlannedItem(
                    plan_day=plan_day,
                    exercise_id=item.exercise_id,
                    sets=item.sets,
                    reps=item.reps,
                    position=item.position,
                )
            )
        created += 1

    db.session.commit()
    return created, skipped


def get_or_create_exercise(name: str) -> Exercise:
    exercise = Exercise.query.filter_by(name=name).one_or_none()
    if exercise is None:
        exercise = Exercise(name=name)
        db.session.add(exercise)
        db.session.flush()
    return exercise


@bp.get("/templates")
def list_templates():
    return render_template(
        "templates_list.html",
        templates=CycleTemplate.query.order_by(CycleTemplate.id).all(),
        today=date.today(),
        max_days=MAX_TEMPLATE_DAYS,
    )


@bp.post("/templates")
def create_template():
    name = (request.form.get("name") or "").strip() or "未命名循环"
    length = parse_sets(request.form.get("length_days")) or 8
    length = max(1, min(length, MAX_TEMPLATE_DAYS))

    template = CycleTemplate(name=name, length_days=length)
    db.session.add(template)
    db.session.flush()

    for index in range(length):
        kind = "rest" if request.form.get(f"kind-{index}") == "rest" else "train"
        title = (request.form.get(f"title-{index}") or "").strip() or None
        template_day = TemplateDay(
            template=template, day_index=index, kind=kind, title=title
        )
        db.session.add(template_day)
        db.session.flush()

        raw_items = (request.form.get(f"items-{index}") or "").splitlines()
        position = 0
        for raw in raw_items:
            exercise_name = raw.strip()
            if not exercise_name:
                continue
            db.session.add(
                TemplateItem(
                    template_day=template_day,
                    exercise=get_or_create_exercise(exercise_name),
                    sets=None,
                    reps=None,
                    position=position,
                )
            )
            position += 1

    db.session.commit()
    return redirect(url_for("cycle.list_templates"), code=303)


@bp.post("/templates/<int:template_id>/apply")
def apply_template_route(template_id: int):
    raw_start = (request.form.get("start") or "").strip()
    try:
        start = date.fromisoformat(raw_start)
    except ValueError:
        return "起始日期没填对", 400

    created, skipped = apply_template(template_id, start)
    return render_template(
        "templates_list.html",
        templates=CycleTemplate.query.order_by(CycleTemplate.id).all(),
        today=date.today(),
        max_days=MAX_TEMPLATE_DAYS,
        message=f"新建 {created} 天，跳过 {skipped} 天（已排过的日期不动）。",
    )
