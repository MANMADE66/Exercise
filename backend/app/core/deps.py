"""鉴权依赖：`Bearer` → 校验 JWT → 查 users → 当前用户（HLD §7、§8 第 1 条）。

约定：
- 除 `POST /auth/register`、`POST /auth/login` 外，所有端点都挂 `get_current_user`
  （本票只交付地基，业务端点随后续票接入）。
- 无 token / 坏 token / 过期 / user 已不存在 —— 一律 401，统一文案，不区分原因
  （与 HLD §9.2 一致；`WWW-Authenticate: Bearer` 是 RFC 6750 的惯例附加信息）。
- `HTTPBearer(auto_error=False)`：默认行为是缺 header 时回 403，这里统一改走 401。
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import TokenPolicy, decode_access_token
from app.db import get_db
from app.models import User

UNAUTHORIZED_DETAIL = "未登录或登录已过期"
UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}

bearer_scheme = HTTPBearer(auto_error=False, description="登录后拿到的 JWT（Bearer）")


def get_token_policy(request: Request) -> TokenPolicy:
    """签发/校验参数来自 lifespan 落盘的密钥与配置（配置在 `app.state.settings`）。"""
    config: Settings = request.app.state.settings
    return TokenPolicy(
        secret=request.app.state.secret_key,
        ttl_days=config.token_ttl_days,
        algorithm=config.jwt_algorithm,
    )


def _unauthorized() -> NoReturn:
    """鉴权失败的唯一出口：401 + 统一文案（不区分缺失/坏/过期/用户已删）。"""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=UNAUTHORIZED_DETAIL,
        headers=UNAUTHORIZED_HEADERS,
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    policy: Annotated[TokenPolicy, Depends(get_token_policy)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """当前登录用户；任何鉴权失败都抛 401（同码同文案）。"""
    if credentials is None or not credentials.credentials:
        _unauthorized()
    user_id = decode_access_token(credentials.credentials, policy)
    if user_id is None:
        _unauthorized()
    user = db.get(User, user_id)
    if user is None:
        _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
TokenPolicyDep = Annotated[TokenPolicy, Depends(get_token_policy)]
