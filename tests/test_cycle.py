from datetime import date

from app.cycle import apply_template
from app.db import db
from app.models import (
    CycleTemplate,
    Exercise,
    PlanDay,
    PlannedItem,
    TemplateDay,
    TemplateItem,
)


def make_8day_template(app):
    with app.app_context():
        e = Exercise(name="卧推")
        t = CycleTemplate(name="八天循环", length_days=8)
        db.session.add_all([e, t])
        db.session.flush()
        for i in range(8):
            kind = "rest" if i in (3, 7) else "train"
            td = TemplateDay(
                template=t,
                day_index=i,
                kind=kind,
                title="胸 + 二头" if i == 0 else None,
            )
            db.session.add(td)
            if i == 0:
                db.session.flush()
                db.session.add(
                    TemplateItem(
                        template_day=td, exercise=e, sets=4, reps="8-12", position=0
                    )
                )
        db.session.commit()
        return t.id


def test_apply_creates_days_and_items(client, app):
    tid = make_8day_template(app)
    with app.app_context():
        created, skipped = apply_template(tid, date(2026, 10, 12))
        assert (created, skipped) == (8, 0)
        assert PlanDay.query.count() == 8
        day1 = PlanDay.query.filter_by(date=date(2026, 10, 12)).one()
        assert day1.kind == "train" and day1.title == "胸 + 二头"
        assert PlannedItem.query.count() == 1
        assert PlannedItem.query.one().weight_kg is None  # 重量不进模板


def test_apply_skips_existing_days_without_overwriting(client, app):
    tid = make_8day_template(app)
    with app.app_context():
        d = PlanDay(date=date(2026, 10, 13), kind="train", title="我自己排的")
        db.session.add(d)
        db.session.commit()
        created, skipped = apply_template(tid, date(2026, 10, 12))
        assert (created, skipped) == (7, 1)
        assert PlanDay.query.filter_by(date=date(2026, 10, 13)).one().title == "我自己排的"


def test_apply_twice_is_fully_skipped(client, app):
    tid = make_8day_template(app)
    with app.app_context():
        apply_template(tid, date(2026, 10, 12))
        assert apply_template(tid, date(2026, 10, 12)) == (0, 8)


def test_templates_page_lists_templates(client, app):
    make_8day_template(app)
    html = client.get("/templates").get_data(as_text=True)
    assert "八天循环" in html
