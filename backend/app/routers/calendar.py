"""月历聚合端点（SRS FR-4、HLD §9.1）。

薄层：解析查询参数 + `CurrentUser` + 聚合返回。`?month=` 非法或缺失时**静默回退当月**
（FR-4.2），不报 400/422 —— 这与 days 端点「日期非法 → 400」是两套错误语义（票 09/10 注释）。
翻月无端点（FR-4.4）：prev/next 由前端算或带 `?month=` 重请。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser
from app.db import get_db
from app.schemas import CalendarAggregate
from app.services import calendar_service

router = APIRouter(tags=["calendar"])


@router.get("/calendar", response_model=CalendarAggregate, summary="月历聚合")
def get_calendar(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    month: str | None = None,
) -> CalendarAggregate:
    return calendar_service.calendar_month(db, user_id=current_user.id, month=month)
