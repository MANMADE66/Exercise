from datetime import date

from app.db import db
from app.models import Exercise, PlanDay, PlannedItem


def test_add_plan_item_creates_exercise_and_item(client, app):
    r = client.post(
        "/day/2026-10-13/plan",
        data={"exercise": "卧推", "weight": "100", "sets": "4", "reps": "8-12"},
    )
    assert r.status_code in (200, 204)
    with app.app_context():
        assert PlanDay.query.filter_by(date=date(2026, 10, 13)).one().kind == "train"
        assert Exercise.query.filter_by(name="卧推").count() == 1
        item = PlannedItem.query.one()
        assert (item.weight_kg, item.sets, item.reps) == (100.0, 4, "8-12")


def test_add_plan_item_reuses_existing_exercise(client, app):
    client.post("/day/2026-10-13/plan", data={"exercise": "卧推", "weight": "100"})
    client.post("/day/2026-10-14/plan", data={"exercise": "卧推", "weight": "102.5"})
    with app.app_context():
        assert Exercise.query.count() == 1
        assert PlannedItem.query.count() == 2


def test_junk_weight_does_not_500(client):
    r = client.post("/day/2026-10-13/plan", data={"exercise": "卧推", "weight": "随便"})
    assert r.status_code in (200, 204)


def test_delete_plan_item(client, app):
    client.post("/day/2026-10-13/plan", data={"exercise": "卧推"})
    with app.app_context():
        pid = PlannedItem.query.one().id
    client.post(f"/plan-item/{pid}/delete")
    with app.app_context():
        assert PlannedItem.query.count() == 0


def test_move_plan_item_changes_order(client, app):
    client.post("/day/2026-10-13/plan", data={"exercise": "卧推"})
    client.post("/day/2026-10-13/plan", data={"exercise": "夹胸"})
    with app.app_context():
        first = PlannedItem.query.filter_by(position=0).one()
        assert first.exercise.name == "卧推"
        second_id = PlannedItem.query.filter_by(position=1).one().id
    client.post(f"/plan-item/{second_id}/move", data={"direction": "up"})
    with app.app_context():
        assert PlannedItem.query.filter_by(position=0).one().exercise.name == "夹胸"
