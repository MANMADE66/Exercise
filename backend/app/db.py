"""引擎、会话工厂、启动建库与 JWT 密钥持久化（HLD §5.1、§5.2、§7）。

设计要点：
- 引擎与会话工厂挂在 `app.state`（由 `main.create_app` 的 lifespan 创建），不在 import
  期碰磁盘——`scripts/export_openapi.py` 只取契约，不会顺手建库或生成密钥。
- 测试用 `dataclasses.replace(settings, data_dir=tmp)` 换库，无需环境变量或模块重载。
- SQLite：`check_same_thread=False`、`journal_mode=WAL`、`PRAGMA foreign_keys=ON`
  （级联与 SET NULL 依赖外键强制开启）。
"""

from __future__ import annotations

import contextlib
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

SECRET_BYTES = 48


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(db_path: Path) -> Engine:
    """SQLite 引擎；`URL.create` 走 `as_posix()`，Windows 路径不会退化成 URL 里的反斜杠。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=db_path.as_posix()),
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """首启建库：建数据目录 → 切 WAL → create_all（无迁移，D8 空库起步）。"""
    with engine.begin() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL"))
    Base.metadata.create_all(engine)


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI 依赖：按请求给一个会话，退出时关闭（事务由 services 提交）。"""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def load_or_create_secret_key(secret_key_path: Path, secret_env: str | None = None) -> str:
    """JWT 签名密钥：环境变量优先，其次 secret.key，都没有则首启生成并落盘。

    重启不失效既有 token（HLD §4.2 第 5 条）；密钥文件在 `backend/data/`（gitignore）。
    """
    if secret_env:
        return secret_env
    if secret_key_path.exists():
        existing = secret_key_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    secret_key_path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(SECRET_BYTES)
    secret_key_path.write_text(key + "\n", encoding="utf-8", newline="\n")
    # 尽量收紧权限（POSIX）；Windows 上 chmod 语义有限，失败不影响功能
    with contextlib.suppress(OSError):
        os.chmod(secret_key_path, 0o600)
    return key
