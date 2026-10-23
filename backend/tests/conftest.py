"""测试固件：每个用例一套临时库（不碰 backend/data）。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from app.core.config import Settings, settings
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def app_settings(tmp_path: Path) -> Settings:
    return replace(
        settings,
        data_dir=tmp_path / "data",
        db_path_override=tmp_path / "data" / "test.db",
        secret_env=None,
    )


@pytest.fixture()
def app(app_settings: Settings) -> FastAPI:
    return create_app(app_settings)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(app: FastAPI, client: TestClient) -> Iterator[Session]:
    """直连同一个临时库的会话（lifespan 已由 client 启动）。"""
    factory: sessionmaker[Session] = app.state.session_factory
    with factory() as session:
        yield session
