"""认证业务规则与事务（HLD §7、SRS FR-1 / FR-2）。

分层约定（AGENTS.md 硬不变量 1）：唯一性判断、哈希、落库与签发 token 都在这里；
routers 只把领域异常映射成 HTTP 状态码（409 / 401），不碰 bcrypt 与密钥细节。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import TokenPolicy, create_access_token, hash_password, verify_password
from app.models import User


class UsernameTakenError(Exception):
    """用户名已被占用（→ 409）。"""


class InvalidCredentialsError(Exception):
    """登录失败：用户名不存在或密码不对，二者不区分（→ 401，SRS FR-2.5）。"""


def register_user(
    db: Session, *, username: str, password: str, policy: TokenPolicy
) -> tuple[User, str]:
    """注册即登录（SRS FR-1.4）：唯一性校验 → bcrypt 落库 → 签发 token。

    唯一键兜底：并发注册同一用户名时预检查会双双通过，此时由 `users.username`
    唯一约束拦下 IntegrityError，转成同一个 409 语义。
    """
    if db.scalar(select(User).where(User.username == username)) is not None:
        raise UsernameTakenError
    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise UsernameTakenError from None
    return user, create_access_token(user.id, policy)


def authenticate_user(
    db: Session, *, username: str, password: str, policy: TokenPolicy
) -> tuple[User, str]:
    """用户名 + 密码 → (user, token)；任一不匹配都抛同一异常（SRS FR-2.5）。"""
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    return user, create_access_token(user.id, policy)
