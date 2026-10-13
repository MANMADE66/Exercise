from datetime import date

from app.db import db
from app.metrics import week_start_for
from app.models import BodyMetric


def test_week_start_is_monday():
    assert week_start_for(date(2026, 10, 13)) == date(2026, 10, 12)
    assert week_start_for(date(2026, 10, 12)) == date(2026, 10, 12)


def test_metric_upsert(client, app):
    client.post("/metrics/2026-10-12", data={"weight": "70.2", "body_fat": "15"})
    client.post("/metrics/2026-10-12", data={"weight": "70.1"})
    with app.app_context():
        assert BodyMetric.query.count() == 1
        assert BodyMetric.query.one().weight_kg == 70.1


def test_bad_weight_does_not_500_and_stores_nothing(client, app):
    r = client.post("/metrics/2026-10-12", data={"weight": "随便"})
    assert r.status_code in (302, 303)  # 回到月历并提示，而不是甩一个裸错误页
    with app.app_context():
        assert BodyMetric.query.count() == 0


def test_calendar_shows_week_weight(client, app):
    client.post("/metrics/2026-10-12", data={"weight": "70.2"})
    assert "70.2" in client.get("/?month=2026-10").get_data(as_text=True)


def test_calendar_shows_metric_for_week_spanning_months(client, app):
    # 2026-11-01 属于 2026-10-26 那一周，10 月的月历那一行要显示它
    client.post("/metrics/2026-10-26", data={"weight": "70.4"})
    assert "70.4" in client.get("/?month=2026-10").get_data(as_text=True)


def test_calendar_shows_metric_for_leading_week(client, app):
    # 2026-10-01 属于 2026-09-28 那一周，10 月的第一行也要能显示它
    client.post("/metrics/2026-09-28", data={"weight": "70.6"})
    assert "70.6" in client.get("/?month=2026-10").get_data(as_text=True)
