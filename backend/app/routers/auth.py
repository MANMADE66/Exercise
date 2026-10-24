"""认证端点（HLD §9.1、SRS FR-1 / FR-2）。

薄层：解析请求体 → 调 service → 领域异常映射成 HTTP 码。
- 注册重复 → 409；字段不合规 → Pydantic 原生 422；
- 登录失败 → 401「用户名或密码不对」（不区分用户名/密码错误，SRS FR-2.5）；
- 登出无端点：纯前端清 localStorage（SRS FR-2.4）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import TokenPolicyDep
from app.db import get_db
from app.models import User
from app.schemas import Credentials, TokenResponse, UserPublic
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]

INVALID_CREDENTIALS_DETAIL = "用户名或密码不对"
USERNAME_TAKEN_DETAIL = "用户名已被占用"


def _to_response(user: User, token: str) -> TokenResponse:
    return TokenResponse(token=token, user=UserPublic(username=user.username))


@router.post(
    "/register",
    response_model=TokenResponse,
    summary="注册并登录",
    responses={409: {"description": USERNAME_TAKEN_DETAIL}},
)
def register(payload: Credentials, db: DbSession, policy: TokenPolicyDep) -> TokenResponse:
    try:
        user, token = auth_service.register_user(
            db, username=payload.username, password=payload.password, policy=policy
        )
    except auth_service.UsernameTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=USERNAME_TAKEN_DETAIL
        ) from None
    return _to_response(user, token)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="登录",
    responses={401: {"description": INVALID_CREDENTIALS_DETAIL}},
)
def login(payload: Credentials, db: DbSession, policy: TokenPolicyDep) -> TokenResponse:
    try:
        user, token = auth_service.authenticate_user(
            db, username=payload.username, password=payload.password, policy=policy
        )
    except auth_service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL
        ) from None
    return _to_response(user, token)
