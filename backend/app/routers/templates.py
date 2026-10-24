"""循环模板端点（SRS FR-9、HLD §9.1、§9.2）。

薄层：只做参数解析 + `CurrentUser` + service 调用。四个端点的返回形状各不同，全部由契约决定：

- `GET /templates` / `DELETE /templates/{id}` → 模板列表（删除后前端整体替换，不再补发 GET）；
- `POST /templates` → 新模板；
- `POST /templates/{id}/apply` → `{created, skipped, skipped_dates}`（FR-9.3）。

`start` 收 JSON 里的字符串再用 `routers/days.py:parse_day_or_400()` 解析：格式非法必须是 **400**
（HLD §9.2「日期格式非法」），标成 `date` 会变成 Pydantic 原生 422。400 文案全仓只有
`INVALID_DATE_DETAIL` 一处，故直接复用那个 helper，不在这里复制第二份消息。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser
from app.core.errors import NOT_FOUND_DETAIL
from app.db import get_db
from app.routers.days import INVALID_DATE_DETAIL, parse_day_or_400
from app.schemas import (
    TemplateAggregate,
    TemplateApplyRequest,
    TemplateApplyResult,
    TemplateCreate,
)
from app.services import template_service

router = APIRouter(prefix="/templates", tags=["templates"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[TemplateAggregate], summary="模板列表")
def list_templates(db: DbSession, current_user: CurrentUser) -> list[TemplateAggregate]:
    """当前用户的全部模板及逐日骨架（FR-9.1）；别人的模板不可见。"""
    return template_service.list_templates(db, user_id=current_user.id)


@router.post("", response_model=TemplateAggregate, summary="创建模板")
def create_template(
    payload: TemplateCreate, db: DbSession, current_user: CurrentUser
) -> TemplateAggregate:
    """建模板（FR-9.2）：名称/天数归一与空动作名忽略都在 service，契约层只收原始输入。"""
    return template_service.create_template(db, user_id=current_user.id, payload=payload)


@router.delete(
    "/{template_id}",
    response_model=list[TemplateAggregate],
    summary="删除模板",
    responses={404: {"description": NOT_FOUND_DETAIL}},
)
def delete_template(
    template_id: int, db: DbSession, current_user: CurrentUser
) -> list[TemplateAggregate]:
    """删除模板（FR-9.4）：天与条目一并级联删除，返回剩余模板列表。"""
    return template_service.delete_template(db, user_id=current_user.id, template_id=template_id)


@router.post(
    "/{template_id}/apply",
    response_model=TemplateApplyResult,
    summary="应用模板",
    responses={400: {"description": INVALID_DATE_DETAIL}, 404: {"description": NOT_FOUND_DETAIL}},
)
def apply_template(
    template_id: int, payload: TemplateApplyRequest, db: DbSession, current_user: CurrentUser
) -> TemplateApplyResult:
    """从 `start` 起逐日铺排（FR-9.3）：已有计划日的日期跳过，绝不覆盖。"""
    return template_service.apply_template(
        db,
        user_id=current_user.id,
        template_id=template_id,
        start=parse_day_or_400(payload.start),
    )
