from datetime import datetime, timezone

from app.db import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Exercise(db.Model):
    __tablename__ = "exercise"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    body_part = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, nullable=False, default=_now)


class PlanDay(db.Model):
    __tablename__ = "plan_day"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False, default="train")
    title = db.Column(db.String(120))
    note = db.Column(db.Text)

    items = db.relationship(
        "PlannedItem",
        back_populates="plan_day",
        cascade="all, delete-orphan",
        order_by="PlannedItem.position",
    )
    actuals = db.relationship(
        "ActualItem",
        back_populates="plan_day",
        cascade="all, delete-orphan",
        order_by="ActualItem.position",
    )
    day_note = db.relationship(
        "DayNote",
        back_populates="plan_day",
        uselist=False,
        cascade="all, delete-orphan",
    )


class PlannedItem(db.Model):
    __tablename__ = "planned_item"

    id = db.Column(db.Integer, primary_key=True)
    plan_day_id = db.Column(db.Integer, db.ForeignKey("plan_day.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    weight_kg = db.Column(db.Float)
    sets = db.Column(db.Integer)
    reps = db.Column(db.String(60))
    position = db.Column(db.Integer, nullable=False, default=0)

    plan_day = db.relationship("PlanDay", back_populates="items")
    exercise = db.relationship("Exercise")


class ActualItem(db.Model):
    __tablename__ = "actual_item"

    id = db.Column(db.Integer, primary_key=True)
    plan_day_id = db.Column(db.Integer, db.ForeignKey("plan_day.id"), nullable=False)
    planned_item_id = db.Column(db.Integer, db.ForeignKey("planned_item.id"))
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    weight_kg = db.Column(db.Float)
    sets = db.Column(db.Integer)
    reps = db.Column(db.String(60))
    position = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.Text)

    plan_day = db.relationship("PlanDay", back_populates="actuals")
    exercise = db.relationship("Exercise")
    planned_item = db.relationship("PlannedItem")


class BodyMetric(db.Model):
    __tablename__ = "body_metric"

    id = db.Column(db.Integer, primary_key=True)
    week_start = db.Column(db.Date, unique=True, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    body_fat_pct = db.Column(db.Float)
    note = db.Column(db.Text)


class DayNote(db.Model):
    __tablename__ = "day_note"

    id = db.Column(db.Integer, primary_key=True)
    plan_day_id = db.Column(
        db.Integer, db.ForeignKey("plan_day.id"), unique=True, nullable=False
    )
    text = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)

    plan_day = db.relationship("PlanDay", back_populates="day_note")


class CycleTemplate(db.Model):
    __tablename__ = "cycle_template"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    length_days = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    days = db.relationship(
        "TemplateDay",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateDay.day_index",
    )


class TemplateDay(db.Model):
    __tablename__ = "template_day"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("cycle_template.id"), nullable=False)
    day_index = db.Column(db.Integer, nullable=False)
    kind = db.Column(db.String(10), nullable=False, default="train")
    title = db.Column(db.String(120))

    template = db.relationship("CycleTemplate", back_populates="days")
    items = db.relationship(
        "TemplateItem",
        back_populates="template_day",
        cascade="all, delete-orphan",
        order_by="TemplateItem.position",
    )


class TemplateItem(db.Model):
    __tablename__ = "template_item"

    id = db.Column(db.Integer, primary_key=True)
    template_day_id = db.Column(
        db.Integer, db.ForeignKey("template_day.id"), nullable=False
    )
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    sets = db.Column(db.Integer)
    reps = db.Column(db.String(60))
    position = db.Column(db.Integer, nullable=False, default=0)

    template_day = db.relationship("TemplateDay", back_populates="items")
    exercise = db.relationship("Exercise")
