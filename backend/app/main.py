"""FastAPI 应用工厂。

启动（lifespan）：建库 + WAL + JWT 密钥落盘（`app/db.py`），引擎与会话工厂挂 `app.state`。
骨架阶段只有 CORS(dev) + health 路由；业务路由随执行票补入，prod 静态托管（D11）同理。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.errors import NotFoundError, not_found_handler
from app.db import create_db_engine, create_session_factory, init_db, load_or_create_secret_key
from app.routers import auth, calendar, days, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config: Settings = app.state.settings
    engine = create_db_engine(config.db_path)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.secret_key = load_or_create_secret_key(config.secret_key_path, config.secret_env)
    try:
        yield
    finally:
        engine.dispose()


def create_app(config: Settings | None = None) -> FastAPI:
    resolved = config or default_settings
    application = FastAPI(title="训练记录 API", version=resolved.version, lifespan=lifespan)
    application.state.settings = resolved

    # 404 的唯一出口：service 抛 NotFoundError，这里统一映射成同码同文案（HLD §9.2）
    application.add_exception_handler(NotFoundError, not_found_handler)

    if resolved.dev_cors:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(calendar.router)
    application.include_router(days.router)
    return application


app = create_app()
