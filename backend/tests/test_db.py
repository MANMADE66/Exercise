"""数据层 schema与运行期约定（HLD §5.2、SRS §4）。"""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.db import load_or_create_secret_key
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

EXPECTED_TABLES = {
    "users",
    "exercise",
    "plan_day",
    "planned_item",
    "actual_item",
    "body_metric",
    "day_note",
    "cycle_template",
    "template_day",
    "template_item",
}


def test_all_ten_tables_created(app: FastAPI, db_session: Session) -> None:
    tables = set(inspect(db_session.get_bind()).get_table_names())

    assert tables == EXPECTED_TABLES


def test_every_business_table_carries_user_id(db_session: Session) -> None:
    inspector = inspect(db_session.get_bind())
    for table in EXPECTED_TABLES - {"users"}:
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert "user_id" in columns, f"{table} 缺少 user_id"


def test_wal_mode_enabled(db_session: Session) -> None:
    assert db_session.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"


def test_foreign_keys_enforced(db_session: Session) -> None:
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_secret_key_generated_and_persisted_once(
    app: FastAPI, app_settings: Settings, client: TestClient
) -> None:
    generated = app.state.secret_key

    assert generated
    assert app_settings.secret_key_path.read_text(encoding="utf-8").strip() == generated
    assert load_or_create_secret_key(app_settings.secret_key_path) == generated
    assert app_settings.secret_key_path.read_text(encoding="utf-8").strip() == generated


def test_secret_key_env_wins_without_touching_disk(tmp_path: Path) -> None:
    secret_path = tmp_path / "data" / "secret.key"

    assert load_or_create_secret_key(secret_path, "from-env") == "from-env"
    assert not secret_path.exists()


def test_default_paths_sit_under_data_dir(tmp_path: Path) -> None:
    config = Settings(data_dir=tmp_path, db_path_override=None)

    assert config.db_path == tmp_path / "app.db"
    assert config.secret_key_path == tmp_path / "secret.key"
