"""密码哈希与 JWT 编解码（HLD §7、SRS FR-1.2 / FR-2.1）。

设计要点：
- bcrypt cost=12；密码哈希只在此模块出现，routers 与 services 都不碰 bcrypt 细节。
- JWT HS256，payload `{sub, iat, exp}`，`sub` 存 user_id 的字符串形式（PyJWT ≥2.10 要求
  `sub` 为字符串，否则解码期即报 `InvalidSubjectError`）。过期判定交给 PyJWT，并强制要求
  `exp`/`iat`/`sub` 三个声明齐全。
- 密码超过 bcrypt 的 72 字节上限时 bcrypt 5.x 会抛 ValueError；本模块用
  `password_too_long()` 暴露判定，由 `schemas.py` 拦成 422，不做静默截断
  （截断会让「长密码的后 72 字节外内容」完全无效，属静默降级）。
- 解码失败一律返回 `None`（坏 token / 过期 / 缺声明 / 签名不符同一出口），
  调用方只需判断 `None` → 401。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

BCRYPT_COST = 12
BCRYPT_MAX_PASSWORD_BYTES = 72
DEFAULT_JWT_ALGORITHM = "HS256"
REQUIRED_CLAIMS = ("sub", "iat", "exp")


def password_byte_length(password: str) -> int:
    """bcrypt 的上限按字节计，不按字符（中文 1 字符 = 3 字节）。"""
    return len(password.encode("utf-8"))


def password_too_long(password: str) -> bool:
    return password_byte_length(password) > BCRYPT_MAX_PASSWORD_BYTES


def hash_password(password: str) -> str:
    """bcrypt(cost=12) 哈希，返回可直接落库的 ASCII 串（`$2b$12$...`）。"""
    if password_too_long(password):
        raise ValueError("password exceeds bcrypt 72-byte limit")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_COST)).decode(
        "ascii"
    )


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码；超长密码直接判否，哈希本身损坏也判否（绝不抛错给请求路径）。"""
    if password_too_long(password):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class TokenPolicy:
    """签发/校验参数：密钥来自 `app.state.secret_key`（env > secret.key > 首启生成）。"""

    secret: str
    ttl_days: int = 7
    algorithm: str = DEFAULT_JWT_ALGORITHM


def create_access_token(user_id: int, policy: TokenPolicy) -> str:
    """签发访问令牌：`{sub: str(user_id), iat, exp = iat + ttl_days}`（SRS FR-2.2）。"""
    issued_at = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(days=policy.ttl_days),
    }
    return jwt.encode(payload, policy.secret, algorithm=policy.algorithm)


def decode_access_token(token: str, policy: TokenPolicy) -> int | None:
    """解码并返回 user_id；坏 token / 过期 / 签名不符 / 缺声明 → `None`。"""
    try:
        payload = jwt.decode(
            token,
            policy.secret,
            algorithms=[policy.algorithm],
            options={"require": list(REQUIRED_CLAIMS)},
        )
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    if not isinstance(subject, str):
        return None
    try:
        return int(subject)
    except ValueError:
        return None
