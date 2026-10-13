from app.db import db
from app.models import DayNote


def test_note_upsert_keeps_one_row(client, app):
    client.post("/day/2026-10-13/note", data={"text": "今天很累"})
    client.post("/day/2026-10-13/note", data={"text": "改主意了：还行"})
    with app.app_context():
        assert DayNote.query.count() == 1
        assert DayNote.query.one().text == "改主意了：还行"


def test_note_shows_in_fragment(client):
    client.post("/day/2026-10-13/note", data={"text": "今天很累"})
    assert "今天很累" in client.get("/day/2026-10-13").get_data(as_text=True)


def test_note_is_per_day(client, app):
    client.post("/day/2026-10-13/note", data={"text": "十三号"})
    client.post("/day/2026-10-14/note", data={"text": "十四号"})
    with app.app_context():
        assert DayNote.query.count() == 2
