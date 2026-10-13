from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import db
from app.models import ActualItem, Exercise, PlanDay, PlannedItem


def test_plan_day_roundtrip(app):
    with app.app_context():
        db.session.add(PlanDay(date=date(2026, 10, 13), kind="train", title="胸 + 二头"))
        db.session.commit()
        row = PlanDay.query.one()
        assert row.kind == "train" and row.title == "胸 + 二头"


def test_planned_and_actual_are_separate_tables(app):
    with app.app_context():
        d = PlanDay(date=date(2026, 10, 13), kind="train")
        e = Exercise(name="卧推")
        db.session.add_all([d, e])
        db.session.flush()
        p = PlannedItem(
            plan_day=d, exercise=e, weight_kg=100, sets=4, reps="8-12", position=0
        )
        db.session.add(p)
        db.session.flush()
        a = ActualItem(
            plan_day=d,
            planned_item=p,
            exercise=e,
            weight_kg=102.5,
            sets=4,
            reps="12/12/10/8",
            position=0,
        )
        db.session.add(a)
        db.session.commit()
        assert PlannedItem.query.one().weight_kg == 100
        assert ActualItem.query.one().planned_item_id == p.id


def test_plan_day_date_is_unique(app):
    with app.app_context():
        db.session.add_all(
            [PlanDay(date=date(2026, 10, 13)), PlanDay(date=date(2026, 10, 13))]
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
