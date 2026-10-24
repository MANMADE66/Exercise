"""Pydantic 请求/响应模型（契约单源：HLD §9；导出到 docs/openapi.json）。

认证部分（HLD §7）：
- 用户名：去首尾空白后 3–20 字符（SRS FR-1.1）；
- 密码：≥ 6 字符，且不超过 bcrypt 的 72 字节上限（超限 422，不静默截断）；
- 校验失败走 Pydantic 原生 422，`detail` 为数组；用 `PydanticCustomError` 给出
  纯中文消息（`ValueError` 会被加 "Value error, " 前缀，不适合直接展示给用户）。
- 响应只回 `{token, user{username}}`：任何字段都不含密码/密码哈希（SRS FR-1.2）。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.security import BCRYPT_MAX_PASSWORD_BYTES, password_too_long

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 20
PASSWORD_MIN_LENGTH = 6

# `CalendarCell` / `DayAggregate` 的字段名就叫 `date`，与 `datetime.date` 同名：在类体里
# `date: date` 会让注解指向字段自身，Pydantic 直接报 unevaluable-type-annotation。故契约里的
# 日期统一用此别名。
IsoDate = date


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


# ---------- 日聚合（SRS FR-5.1、HLD §9.1） ----------
# 形状一次定好：`GET /days/{iso_date}` 与全部日级写操作（FR-6.5 / FR-7.5 / FR-8.3）共用同一个
# 响应模型，前端整体替换状态（D7），写完不再补发 GET。


class PlannedItemOut(BaseModel):
    """计划条目：动作只出名字（动作库按用户隔离且 (user_id, name) 唯一，名字即身份）。"""

    id: int = Field(description="计划条目 id（删除、上下移用）")
    exercise: str = Field(description="动作名（已建入本人动作库）")
    weight_kg: float | None = Field(default=None, description="计划重量（kg），解析失败为 null")
    sets: int | None = Field(default=None, description="组数，解析失败为 null")
    reps: str | None = Field(default=None, description="次数，自由文本（如 8-12）")
    position: int = Field(description="当天顺序，从 0 起连续")


class ActualItemOut(BaseModel):
    """实际条目；`planned_item_id` 为 null 表示计划外新增（FR-7.3）。"""

    id: int = Field(description="实际条目 id（行内更新、删除用）")
    planned_item_id: int | None = Field(
        default=None, description="对应的计划条目 id；计划外条目为 null"
    )
    exercise: str = Field(description="动作名")
    weight_kg: float | None = Field(default=None, description="实际重量（kg）")
    sets: int | None = Field(default=None, description="实际组数")
    reps: str | None = Field(default=None, description="实际次数，自由文本")
    note: str | None = Field(default=None, description="该行备注")
    position: int = Field(description="当天顺序，从 0 起连续")


class DayAggregate(BaseModel):
    """一天的全部数据（FR-5.1）。

    无记录的日期：`kind` / `title` 为 null、两个集合为空、`note` 为空串 —— 前端不需要区分
    「没排计划」与「空字段」，也绝不因为读一次就凭空多出一个 PlanDay（FR-5.2）。
    """

    date: IsoDate = Field(description="请求的日期（YYYY-MM-DD）")
    kind: Literal["train", "rest"] | None = Field(
        default=None, description="训练日 / 休息日；当天没有 PlanDay 时为 null"
    )
    title: str | None = Field(default=None, description="当天标题；当天没有 PlanDay 时为 null")
    planned_items: list[PlannedItemOut] = Field(
        default_factory=list, description="全部计划条目，按 position 升序"
    )
    actual_items: list[ActualItemOut] = Field(
        default_factory=list, description="全部实际条目，按 position 升序"
    )
    note: str = Field(default="", description="感受笔记；没有记录时为空串")


class BodyMetricOut(BaseModel):
    """周体重（SRS FR-10）：月历周行的只读展示；票 15 的写入端点复用同一形状。"""

    week_start: IsoDate = Field(description="周起点，恒为周一")
    weight_kg: float = Field(description="体重（公斤）")
    body_fat_pct: float | None = Field(default=None, description="体脂率（百分比）")
    note: str | None = Field(default=None, description="备注")


class CalendarCell(BaseModel):
    """月历网格的一格。

    `kind` / `title` 为 `null` 表示该日没有 PlanDay（还没排计划），这与补齐位是两回事：
    补齐位（月初日前 / 月末日后）在 `CalendarWeek.cells` 里直接是 `null`，不是空格子。
    """

    date: IsoDate = Field(description="日期")
    kind: Literal["train", "rest"] | None = Field(default=None, description="计划日类型")
    title: str | None = Field(default=None, description="计划日标题；无标题训练日不显示标签")


class CalendarWeek(BaseModel):
    """月历的一行（一个自然周）：7 格 + 该周体重。"""

    week_start: IsoDate = Field(description="周起点，该周第一个日期的周一（可能落在上一个月）")
    cells: list[CalendarCell | None] = Field(description="7 格，周一为第一列；补齐位为 null")
    metric: BodyMetricOut | None = Field(default=None, description="该周的体重记录，没填就是 null")


class CalendarAggregate(BaseModel):
    """月历聚合（SRS FR-4）：整周网格 + 概要 + 已记录日期 + 周体重。"""

    year: int = Field(description="生效年份（?month 非法或缺失时已回退为当月）")
    month: int = Field(description="生效月份 1–12")
    weeks: list[CalendarWeek] = Field(description="按周排列的网格，首行不一定是当月 1 日")
    logged_dates: list[IsoDate] = Field(
        description="存在实际条目的日期集合（升序；不是「存在计划日」的日期）"
    )
