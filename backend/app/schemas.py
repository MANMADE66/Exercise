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

# 计划日类型只有两值（models 默认 `train`）。日聚合与月历都暴露它，故单源在契约层：两个 service
# 把 ORM 的裸 `str` 收窄时指向同一别名，而不是一处 `cast` 一处 `type: ignore`。
DayKind = Literal["train", "rest"]


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
    kind: DayKind | None = Field(
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


# ---------- 计划条目写请求（SRS FR-6、HLD §9.1） ----------
# 重量 / 组数 / 次数收**原始文本**：容错解析属于 service（FR-6.4），契约只声明「用户手写的东西」。
# 若在这里标成 float / int，`"60kg"` 会被 Pydantic 直接 422 拦掉，正好违背「解析失败不报错」。

MoveDirection = Literal["up", "down"]


class _ExerciseNamed(BaseModel):
    """计划条目与实际条目共用的动作名规则：去首尾空白后不能为空。

    空动作名 422 而不是静默丢掉这条输入（票 11 裁定，v1 是静默 no-op）；实际条目的计划外新增
    （FR-7.3）与计划条目同构，故规则只此一份。
    """

    exercise: str = Field(description="动作名，去首尾空白后不能为空")

    @field_validator("exercise")
    @classmethod
    def _require_exercise(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise PydanticCustomError("exercise_required", "动作名不能为空")
        return normalized


class PlanItemCreate(_ExerciseNamed):
    """添加计划条目（FR-6.1）：动作名自动建入本人动作库，新条目置于当天末位。"""

    weight: str | None = Field(default=None, description="重量原文本，如 60 / 60kg / 62,5")
    sets: str | None = Field(default=None, description="组数原文本，如 4")
    reps: str | None = Field(default=None, description="次数原文本，自由文本如 8-12")


class PlanItemMove(BaseModel):
    """上下移动（FR-6.3）：已在边界（首个上移 / 末个下移）时静默成功。"""

    direction: MoveDirection = Field(description="up 上移 / down 下移")


# ---------- 实际条目写请求（SRS FR-7、HLD §9.1） ----------


class ActualItemCreate(_ExerciseNamed):
    """新增计划外实际条目（FR-7.3）：结构与计划条目一致，另可带备注。"""

    weight: str | None = Field(default=None, description="实际重量原文本，如 60 / 60kg / 62,5")
    sets: str | None = Field(default=None, description="实际组数原文本，如 4")
    reps: str | None = Field(default=None, description="实际次数原文本，自由文本如 8-12")
    note: str | None = Field(default=None, description="该行备注；空串或纯空白视为未填")


class ActualItemUpdate(BaseModel):
    """行内自动保存（FR-7.2）：逐字段更新重量/组数/次数/备注，**三态**语义。

    - 字段缺省 → 不动（不因为只改重量就清掉备注）；
    - 显式 `null` → 该字段置空；
    - 空串 → 该字段置 NULL / 空（与原文版一致）。

    「缺省」与「显式 null」都是 `None`，值本身分不出来，只能靠 `model_fields_set` 逐字段判
    （service 侧）。契约层把三者都收进来：`str | None` 的 `None` 表示「置空」，缺席表示「不动」。
    """

    weight: str | None = Field(
        default=None, description="实际重量原文本；缺省不动，null 或空串置空"
    )
    sets: str | None = Field(default=None, description="实际组数原文本；缺省不动，null 或空串置空")
    reps: str | None = Field(default=None, description="实际次数原文本；缺省不动，null 或空串置空")
    note: str | None = Field(default=None, description="该行备注；缺省不动，null 或空串置空")


# ---------- 感受笔记（SRS FR-8、HLD §9.1） ----------


class DayNoteUpdate(BaseModel):
    """整段保存感受文本（FR-8.1）。

    `text` **必填**：PUT 的语义是「整段替换」，缺省不应该静默地被当成「清空」—— 真要清空就
    显式传空串（服务端 trim 后落库为空文本，仍保留 DayNote 行，见 FR-8.1「为空字符串时仍保存」）。
    """

    text: str = Field(description="感受原文；空串合法，含义为清空（不删 DayNote 行）")


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
    kind: DayKind | None = Field(default=None, description="计划日类型")
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
