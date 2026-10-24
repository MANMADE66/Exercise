"""周体重端点（SRS FR-10、HLD §9.1）。

薄层：解析路径参数 + `CurrentUser` + service upsert 返回**该周 metric**（不是月历聚合：写周体重
只影响一行，前端按返回的 metric 改那一格，不必重发 `GET /calendar`）。

两条错误语义，各自一处：

- `week_start` 日期格式非法 → **400**（HLD §9.2「日期格式非法」）。直接复用
  `routers/days.parse_day_or_400`：同为「ISO 日期路径参数认不出」，文案不该有第二份；
- 体重非法 → **422**，且**不落库**（FR-10.2）。这关在契约层 `BodyMetricUpdate.weight` 的
  validator 上（Pydantic 原生 422；`api.ts` 会把数组 detail 拼成中文串展示）。

路径参数虽然叫 `week_start`，但**不假设调用方传的是周一**：归一在 service（`week_start_for`），
传周三也落到该周周一那一行（票 15 裁定，与 v1 一致）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser
from app.db import get_db
from app.routers.days import INVALID_DATE_DETAIL, parse_day_or_400
from app.schemas import WEIGHT_INVALID_MESSAGE, BodyMetricOut, BodyMetricUpdate
from app.services import metrics_service

router = APIRouter(tags=["metrics"])


@router.put(
    "/metrics/{week_start}",
    response_model=BodyMetricOut,
    summary="保存周体重",
    responses={
        400: {"description": INVALID_DATE_DETAIL},
        422: {"description": WEIGHT_INVALID_MESSAGE},
    },
)
def save_metric(
    week_start: str,
    payload: BodyMetricUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
) -> BodyMetricOut:
    """按 `(user_id, 周起点)` upsert（FR-10.1）：路径日期归一到周一，同周再 PUT 只更新那一行。"""
    return metrics_service.upsert_week_metric(
        db,
        user_id=current_user.id,
        day=parse_day_or_400(week_start),
        weight=payload.weight,
        body_fat=payload.body_fat,
        note=payload.note,
    )
