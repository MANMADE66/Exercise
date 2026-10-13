from datetime import date

from app.calendar import month_grid


def test_month_grid_starts_on_monday_and_pads():
    weeks = month_grid(2026, 10)  # 2026-10-01 是周四
    assert len(weeks) == 5
    assert weeks[0][:3] == [None, None, None]
    assert weeks[0][3] == date(2026, 10, 1)
    assert weeks[4][5] == date(2026, 10, 31)
    assert weeks[4][6] is None


def test_month_grid_february():
    assert sum(1 for w in month_grid(2026, 2) for d in w if d) == 28
    assert sum(1 for w in month_grid(2024, 2) for d in w if d) == 29


def test_calendar_route_renders_month(client):
    html = client.get("/?month=2026-10").get_data(as_text=True)
    assert 'data-date="2026-10-01"' in html
    assert 'data-date="2026-10-31"' in html
    assert 'data-date="2026-11-01"' not in html


def test_calendar_route_defaults_to_current_month(client):
    assert client.get("/").status_code == 200


def test_calendar_shows_train_day_title(client, app):
    from app.db import db
    from app.models import PlanDay

    with app.app_context():
        db.session.add(PlanDay(date=date(2026, 10, 13), kind="train", title="胸 + 二头"))
        db.session.commit()

    html = client.get("/?month=2026-10").get_data(as_text=True)
    assert "胸 + 二头" in html
