"""存活探针：骨架的最小可调用端点，同时给 OpenAPI 生成链提供第一个 schema。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="存活探针")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=settings.version)
