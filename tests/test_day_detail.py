from datetime import date

import pytest

from app.db import db
from app.models import ActualItem, Exercise, PlanDay, PlannedItem


@pytest.fixture
def seeded(app):
    with app.app_context():
        d = PlanDay(date=date(2026, 10, 13), kind="train", title="胸 + 二头")
        e = Exercise(name="卧推")
        db.session.add_all([d, e])
        db.session.flush()
        db.session.add(
            PlannedItem(
                plan_day=d, exercise=e, weight_kg=100, sets=4, reps="8-12", position=0
            )
        )
        db.session.add(
            ActualItem(
                plan_day=d,
                exercise=e,
                weight_kg=95,
                sets=3,
                reps="12/10/8",
                position=0,
                note="最后一组没做完",
            )
        )
        db.session.commit()


def test_day_fragment_has_two_separate_sections(client, seeded):
    html = client.get("/day/2026-10-13").get_data(as_text=True)
    assert 'id="planned"' in html and 'id="actual"' in html
    assert html.index('id="planned"') < html.index('id="actual"')
    assert "卧推" in html and "100" in html and "95" in html
    assert "最后一组没做完" in html


def test_day_fragment_for_empty_day_has_both_sections(client):
    html = client.get("/day/2026-10-20").get_data(as_text=True)
    assert 'id="planned"' in html and 'id="actual"' in html
    assert "None" not in html


def test_day_fragment_never_touches_other_days(client, seeded):
    html = client.get("/day/2026-10-14").get_data(as_text=True)
    assert "卧推" not in html


def test_day_fragment_rejects_bad_date(client):
    assert client.get("/day/not-a-date").status_code == 400
