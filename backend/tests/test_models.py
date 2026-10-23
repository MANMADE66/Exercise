"""表级约束与级联语义（SRS FR-3.1、FR-6.2、HLD §5.2）。"""

from __future__ import annotations

from datetime import date

import pytest
from app.models import (
    ActualItem,
    BodyMetric,
    CycleTemplate,
    DayNote,
    Exercise,
    PlanDay,
    PlannedItem,
    TemplateDay,
    TemplateItem,
    User,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _user(session: Session, username: str) -> User:
    user = User(username=username, password_hash="hash")
    session.add(user)
    session.flush()
    return user


def _exercise(session: Session, user: User, name: str) -> Exercise:
    exercise = Exercise(user_id=user.id, name=name)
    session.add(exercise)
    session.flush()
    return exercise


def _plan_day(session: Session, user: User, day: date) -> PlanDay:
    plan_day = PlanDay(user_id=user.id, date=day, kind="train", title="上肢")
    session.add(plan_day)
    session.flush()
    return plan_day


def test_exercise_names_are_scoped_per_user(db_session: Session) -> None:
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")

    _exercise(db_session, alice, "深蹲")
    _exercise(db_session, bob, "深蹲")  # 不同用户可同名（FR-3.4）

    with pytest.raises(IntegrityError):
        _exercise(db_session, alice, "深蹲")
    db_session.rollback()


def test_plan_day_is_unique_per_user(db_session: Session) -> None:
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    day = date(2026, 10, 23)

    _plan_day(db_session, alice, day)
    _plan_day(db_session, bob, day)

    with pytest.raises(IntegrityError):
        _plan_day(db_session, alice, day)
    db_session.rollback()


def test_body_metric_is_unique_per_user_and_week(db_session: Session) -> None:
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    monday = date(2026, 10, 19)

    db_session.add_all(
        [
            BodyMetric(user_id=alice.id, week_start=monday, weight_kg=70.5),
            BodyMetric(user_id=bob.id, week_start=monday, weight_kg=80.2),
        ]
    )
    db_session.flush()

    db_session.add(BodyMetric(user_id=alice.id, week_start=monday, weight_kg=71.0))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_template_day_index_is_unique_per_template(db_session: Session) -> None:
    alice = _user(db_session, "alice")
    template = CycleTemplate(user_id=alice.id, name="上肢循环", length_days=8)
    db_session.add(template)
    db_session.flush()

    db_session.add(TemplateDay(user_id=alice.id, template_id=template.id, day_index=1))
    db_session.flush()

    db_session.add(TemplateDay(user_id=alice.id, template_id=template.id, day_index=1))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_prefill_duplicate_actual_item_rejected_but_extra_allowed(
    db_session: Session,
) -> None:
    alice = _user(db_session, "alice")
    squat = _exercise(db_session, alice, "深蹲")
    plan_day = _plan_day(db_session, alice, date(2026, 10, 23))
    planned = PlannedItem(
        user_id=alice.id, plan_day_id=plan_day.id, exercise_id=squat.id, position=0
    )
    db_session.add(planned)
    db_session.flush()

    db_session.add(
        ActualItem(
            user_id=alice.id,
            plan_day_id=plan_day.id,
            planned_item_id=planned.id,
            exercise_id=squat.id,
            position=0,
        )
    )
    db_session.flush()

    db_session.add(
        ActualItem(
            user_id=alice.id,
            plan_day_id=plan_day.id,
            planned_item_id=planned.id,
            exercise_id=squat.id,
            position=1,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # planned_item_id 为 NULL 的计划外条目可有多条（SQLite 视 NULL 互不相等）
    alice = _user(db_session, "alice2")
    squat = _exercise(db_session, alice, "深蹲")
    plan_day = _plan_day(db_session, alice, date(2026, 10, 24))
    db_session.add_all(
        [
            ActualItem(user_id=alice.id, plan_day_id=plan_day.id, exercise_id=squat.id, position=0),
            ActualItem(user_id=alice.id, plan_day_id=plan_day.id, exercise_id=squat.id, position=1),
        ]
    )
    db_session.flush()


def test_deleting_plan_day_cascades_items_actuals_and_note(db_session: Session) -> None:
    alice = _user(db_session, "alice")
    squat = _exercise(db_session, alice, "深蹲")
    plan_day = _plan_day(db_session, alice, date(2026, 10, 23))
    planned = PlannedItem(
        user_id=alice.id, plan_day_id=plan_day.id, exercise_id=squat.id, position=0
    )
    db_session.add(planned)
    db_session.flush()
    db_session.add_all(
        [
            ActualItem(
                user_id=alice.id,
                plan_day_id=plan_day.id,
                planned_item_id=planned.id,
                exercise_id=squat.id,
                position=0,
            ),
            DayNote(user_id=alice.id, plan_day_id=plan_day.id, text="状态不错"),
        ]
    )
    db_session.flush()

    db_session.delete(plan_day)
    db_session.flush()

    assert db_session.scalar(select(func.count()).select_from(PlannedItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(ActualItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(DayNote)) == 0


def test_deleting_planned_item_keeps_actual_with_null_link(db_session: Session) -> None:
    alice = _user(db_session, "alice")
    squat = _exercise(db_session, alice, "深蹲")
    plan_day = _plan_day(db_session, alice, date(2026, 10, 23))
    planned = PlannedItem(
        user_id=alice.id, plan_day_id=plan_day.id, exercise_id=squat.id, position=0
    )
    db_session.add(planned)
    db_session.flush()
    actual = ActualItem(
        user_id=alice.id,
        plan_day_id=plan_day.id,
        planned_item_id=planned.id,
        exercise_id=squat.id,
        position=0,
        weight_kg=100.0,
    )
    db_session.add(actual)
    db_session.flush()
    actual_id = actual.id

    db_session.delete(planned)
    db_session.flush()
    db_session.expire_all()

    kept = db_session.get(ActualItem, actual_id)
    assert kept is not None
    assert kept.planned_item_id is None
    assert kept.weight_kg == 100.0


def test_deleting_cycle_template_cascades_days_and_items(db_session: Session) -> None:
    alice = _user(db_session, "alice")
    squat = _exercise(db_session, alice, "深蹲")
    template = CycleTemplate(user_id=alice.id, name="上肢循环", length_days=8)
    db_session.add(template)
    db_session.flush()
    template_day = TemplateDay(user_id=alice.id, template_id=template.id, day_index=0)
    db_session.add(template_day)
    db_session.flush()
    db_session.add(
        TemplateItem(
            user_id=alice.id,
            template_day_id=template_day.id,
            exercise_id=squat.id,
            sets=5,
            reps="5",
            position=0,
        )
    )
    db_session.flush()

    db_session.delete(template)
    db_session.flush()

    assert db_session.scalar(select(func.count()).select_from(TemplateDay)) == 0
    assert db_session.scalar(select(func.count()).select_from(TemplateItem)) == 0
