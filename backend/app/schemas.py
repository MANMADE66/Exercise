"""Pydantic 请求/响应模型（契约单源：HLD §9；导出到 docs/openapi.json）。

认证部分（HLD §7）：
- 用户名：去首尾空白后 3–20 字符（SRS FR-1.1）；
- 密码：≥ 6 字符，且不超过 bcrypt 的 72 字节上限（超限 422，不静默截断）；
- 校验失败走 Pydantic 原生 422，`detail` 为数组；用 `PydanticCustomError` 给出
  纯中文消息（`ValueError` 会被加 "Value error, " 前缀，不适合直接展示给用户）。
- 响应只回 `{token, user{username}}`：任何字段都不含密码/密码哈希（SRS FR-1.2）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.security import BCRYPT_MAX_PASSWORD_BYTES, password_too_long

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 20
PASSWORD_MIN_LENGTH = 6


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="服务状态")
    version: str = Field(description="API 版本号")


class Credentials(BaseModel):
    """注册与登录共用（两端字段与校验完全一致，前端也只消费这一种形状）。"""

    username: str = Field(description="用户名，去首尾空白后 3–20 个字符")
    password: str = Field(description="密码，至少 6 个字符")

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not USERNAME_MIN_LENGTH <= len(normalized) <= USERNAME_MAX_LENGTH:
            raise PydanticCustomError(
                "username_length",
                f"用户名长度需为 {USERNAME_MIN_LENGTH}–{USERNAME_MAX_LENGTH} 个字符",
            )
        return normalized

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        if len(value) < PASSWORD_MIN_LENGTH:
            raise PydanticCustomError("password_length", f"密码至少 {PASSWORD_MIN_LENGTH} 位")
        if password_too_long(value):
            raise PydanticCustomError(
                "password_too_long",
                f"密码最长 {BCRYPT_MAX_PASSWORD_BYTES} 字节（约 72 个英文字符）",
            )
        return value


class UserPublic(BaseModel):
    """对外可见的用户身份（用户名即身份，SRS §2.2；永不返回密码字段）。"""

    username: str = Field(description="用户名")


class TokenResponse(BaseModel):
    token: str = Field(description="JWT，前端存 localStorage 并在后续请求带 Bearer")
    user: UserPublic = Field(description="当前用户")
