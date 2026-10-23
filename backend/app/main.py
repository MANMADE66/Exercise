"""FastAPI 应用工厂。

骨架阶段：CORS(dev) + health 路由。静态托管（prod）与业务路由随后续票补入。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health


def create_app() -> FastAPI:
    app = FastAPI(title="训练记录 API", version=settings.version)

    if settings.dev_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    return app


app = create_app()
