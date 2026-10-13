from datetime import date

from app.db import db
from app.models import ActualItem, Exercise, PlanDay, PlannedItem


def seed_plan(app):
    with app.app_context():
        d = PlanDay(date=date(2026, 10, 13), kind="train")
        e = Exercise(name="卧推")
        db.session.add_all([d, e])
        db.session.flush()
        db.session.add(
            PlannedItem(
                plan_day=d, exercise=e, weight_kg=100, sets=4, reps="8-12", position=0
            )
        )
        db.session.commit()


def test_prefill_copies_plan_without_losing_link(client, app):
    seed_plan(app)
    client.post("/day/2026-10-13/actual/prefill")
    with app.app_context():
        a = ActualItem.query.one()
        assert a.weight_kg == 100 and a.sets == 4 and a.reps == "8-12"
        assert a.planned_item_id == PlannedItem.query.one().id


def test_prefill_is_idempotent(client, app):
    seed_plan(app)
    client.post("/day/2026-10-13/actual/prefill")
    client.post("/day/2026-10-13/actual/prefill")
    with app.app_context():
        assert ActualItem.query.count() == 1


def test_prefill_keeps_manual_edits(client, app):
    seed_plan(app)
    client.post("/day/2026-10-13/actual/prefill")
    with app.app_context():
        aid = ActualItem.query.one().id
    client.post(
        "/day/2026-10-13/actual",
        data={"id": str(aid), "weight": "95", "sets": "3", "reps": "10/8", "note": "没做完"},
    )
    client.post("/day/2026-10-13/actual/prefill")
    with app.app_context():
        a = ActualItem.query.one()
        assert (a.weight_kg, a.sets, a.note) == (95.0, 3, "没做完")


def test_add_extra_actual_item_without_plan(client, app):
    client.post("/day/2026-10-13/actual", data={"exercise": "哑铃弯举", "weight": "12"})
    with app.app_context():
        a = ActualItem.query.one()
        assert a.planned_item_id is None and a.exercise.name == "哑铃弯举"


def test_delete_actual_item(client, app):
    client.post("/day/2026-10-13/actual", data={"exercise": "哑铃弯举"})
    with app.app_context():
        aid = ActualItem.query.one().id
    client.post(f"/actual-item/{aid}/delete")
    with app.app_context():
        assert ActualItem.query.count() == 0


def test_prefill_without_plan_is_harmless(client, app):
    r = client.post("/day/2026-10-13/actual/prefill")
    assert r.status_code == 200
    with app.app_context():
        assert ActualItem.query.count() == 0


def test_actual_row_default_submit_is_save_not_delete(client, app):
    """在行内输入框里按回车，浏览器会点第一个 submit 按钮——它必须是保存，不能是删除。"""
    client.post("/day/2026-10-13/actual", data={"exercise": "哑铃弯举"})
    html = client.get("/day/2026-10-13").get_data(as_text=True)
    row = html[html.index('class="row-form"') :]
    row = row[: row.index("</form>")]
    assert "data-default-submit" in row
    assert row.index("data-default-submit") < row.index("formaction")
