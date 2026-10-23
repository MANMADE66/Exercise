"""10 张表 ORM：v1 的 9 表（沿用原表名）+ users（SRS §4、HLD §5.2）。

隔离约定（SRS FR-3.1）：每张业务表都带 `user_id` 外键；唯一键由「全局唯一」
收紧为「(user_id, 原键)」或经父链唯一。

级联约定（HLD §5.2）：
- 删 plan_day → 级联 planned_item / actual_item / day_note（ORM cascade + FK ON DELETE CASCADE）；
- 删 planned_item → **不**级联 actual_item，仅把 planned_item_id 置空（FK ON DELETE SET NULL，
  历史记录保留，SRS FR-6.2）；
- 删 cycle_template → 级联 template_day → template_item。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """统一 UTC 存储（SRS §4），展示层不做时区换算。"""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UserScoped:
    """业务表共用：user_id 外键（隔离的落点，SRS FR-3.1）。"""

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Exercise(UserScoped, Base):
    """动作库按用户独立（SRS FR-3.4）：(user_id, name) 唯一。"""

    __tablename__ = "exercise"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_exercise_user_id_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    body_part: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class PlanDay(UserScoped, Base):
    """(user_id, date) 唯一；date 建索引供月历按区间取数（HLD §5.2）。"""

    __tablename__ = "plan_day"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_plan_day_user_id_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="train")
    title: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[PlannedItem]] = relationship(
        back_populates="plan_day",
        cascade="all, delete-orphan",
        order_by="PlannedItem.position",
    )
    actuals: Mapped[list[ActualItem]] = relationship(
        back_populates="plan_day",
        cascade="all, delete-orphan",
        order_by="ActualItem.position",
    )
    day_note: Mapped[DayNote | None] = relationship(
        back_populates="plan_day",
        cascade="all, delete-orphan",
        uselist=False,
    )


class PlannedItem(UserScoped, Base):
    __tablename__ = "planned_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_day_id: Mapped[int] = mapped_column(
        ForeignKey("plan_day.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id"), nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    sets: Mapped[int | None] = mapped_column(Integer)
    reps: Mapped[str | None] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    plan_day: Mapped[PlanDay] = relationship(back_populates="items")
    exercise: Mapped[Exercise] = relationship()
    actual_items: Mapped[list[ActualItem]] = relationship(
        back_populates="planned_item",
        # 不级联删除：删计划条目时仅置空 actual_item.planned_item_id（SRS FR-6.2）
        passive_deletes=True,
    )


class ActualItem(UserScoped, Base):
    """UNIQUE(plan_day_id, planned_item_id)：prefill 幂等加固（HLD §5.2）。

    planned_item_id 可空；SQLite 把 NULL 视为互不相等，故计划外条目不受唯一约束影响。
    """

    __tablename__ = "actual_item"
    __table_args__ = (
        UniqueConstraint(
            "plan_day_id", "planned_item_id", name="uq_actual_item_plan_day_id_planned_item_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_day_id: Mapped[int] = mapped_column(
        ForeignKey("plan_day.id", ondelete="CASCADE"), nullable=False, index=True
    )
    planned_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("planned_item.id", ondelete="SET NULL"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id"), nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    sets: Mapped[int | None] = mapped_column(Integer)
    reps: Mapped[str | None] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text)

    plan_day: Mapped[PlanDay] = relationship(back_populates="actuals")
    exercise: Mapped[Exercise] = relationship()
    planned_item: Mapped[PlannedItem | None] = relationship(back_populates="actual_items")


class BodyMetric(UserScoped, Base):
    """周体重：(user_id, week_start) 唯一，week_start 恒为周一（SRS FR-10）。"""

    __tablename__ = "body_metric"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_body_metric_user_id_week_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)


class DayNote(UserScoped, Base):
    """一天一条感受笔记：plan_day_id 唯一（1:1，隔离已由父链承担）。"""

    __tablename__ = "day_note"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_day_id: Mapped[int] = mapped_column(
        ForeignKey("plan_day.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    plan_day: Mapped[PlanDay] = relationship(back_populates="day_note")


class CycleTemplate(UserScoped, Base):
    __tablename__ = "cycle_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    length_days: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    days: Mapped[list[TemplateDay]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateDay.day_index",
    )


class TemplateDay(UserScoped, Base):
    __tablename__ = "template_day"
    __table_args__ = (
        UniqueConstraint("template_id", "day_index", name="uq_template_day_template_id_day_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("cycle_template.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="train")
    title: Mapped[str | None] = mapped_column(String(120))

    template: Mapped[CycleTemplate] = relationship(back_populates="days")
    items: Mapped[list[TemplateItem]] = relationship(
        back_populates="template_day",
        cascade="all, delete-orphan",
        order_by="TemplateItem.position",
    )


class TemplateItem(UserScoped, Base):
    """模板条目不含重量（SRS FR-9.2）。"""

    __tablename__ = "template_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_day_id: Mapped[int] = mapped_column(
        ForeignKey("template_day.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercise.id"), nullable=False)
    sets: Mapped[int | None] = mapped_column(Integer)
    reps: Mapped[str | None] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template_day: Mapped[TemplateDay] = relationship(back_populates="items")
    exercise: Mapped[Exercise] = relationship()
