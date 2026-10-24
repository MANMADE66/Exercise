"""感受笔记保存（SRS FR-8、HLD §9.1/§9.2、§12.0「days」行）。

覆盖点：
- 整段保存与覆盖：trim 后落库，GET 原样回（存进去是什么就回什么）；
- 空串 / 纯空白 = 清空原文，但**不删 DayNote 行**（FR-8.1「为空字符串时仍保存」）；
- 隐式建日规则（FR-8.2）：无 PlanDay 且文本（trim 后）非空才建日，建出来是 `train` / 无标题；
  无 PlanDay 且文本为空 → **一行都不写**（plan_day / day_note 两表计数都不变）；
- 契约：`text` 必填（缺省 422，不静默当清空）；非法日期 400；无 token 401；
- 隔离：B 写同一天落到 B 自己名下（唯一键是 `(user_id, date)`），A 的笔记一个字都不变；
- 并发：首次写入撞 `plan_day_id` 唯一键时复用对方插的行并覆盖文本，不冒 500。
"""

from __future__ import annotations

from datetime import date

import pytest
from app.models import DayNote, PlanDay
from app.routers.days import INVALID_DATE_DETAIL
from app.schemas import DayAggregate
from app.services import days_service
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import Actor, Factories

DAY = date(2026, 1, 5)
ISO = "2026-01-05"


def _put(client: TestClient, actor: Actor, text: str, iso_date: str = ISO) -> DayAggregate:
    response = client.put(f"/days/{iso_date}/note", json={"text": text}, headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _get_note(client: TestClient, actor: Actor, iso_date: str = ISO) -> str:
    response = client.get(f"/days/{iso_date}", headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json()).note


def _plan_day_count(db: Session) -> int:
    return int(db.scalar(select(func.count(PlanDay.id))) or 0)


def _note_count(db: Session) -> int:
    return int(db.scalar(select(func.count(DayNote.id))) or 0)


# ---------- 保存与覆盖 ----------


def test_save_creates_plan_day_and_note(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """FR-8.2：文本非空且当天无 PlanDay → 隐式建 train 日 + 落笔记。"""
    body = _put(client, actor_a, "  今天有点累  ")

    assert body.kind == "train"
    assert body.title is None
    assert body.note == "今天有点累"
    assert body.planned_items == []
    assert body.actual_items == []

    db_session.expire_all()
    assert _plan_day_count(db_session) == 1
    assert _note_count(db_session) == 1
    assert _get_note(client, actor_a) == "今天有点累"


def test_save_overwrites_existing_note(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """第二次保存是覆盖而不是新增行（day_note.plan_day_id 唯一）。"""
    day = make.plan_day(actor_a, DAY, title="下肢")
    db_session.add(DayNote(user_id=actor_a.user_id, plan_day_id=day.id, text="旧内容"))
    db_session.commit()

    body = _put(client, actor_a, "新内容")

    assert body.note == "新内容"
    assert body.title == "下肢"  # 已有计划日的 kind/title 不被写路径覆盖
    db_session.expire_all()
    assert _note_count(db_session) == 1
    assert _plan_day_count(db_session) == 1


def test_save_does_not_touch_other_independent_fields(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """写笔记只动 DayNote：计划条目与实际条目原样返回。"""
    day = make.plan_day(actor_a, DAY)
    make.planned_item(actor_a, day, exercise="深蹲", sets=5)
    make.actual_item(actor_a, day, exercise="深蹲", sets=4)

    body = _put(client, actor_a, "做完爽")

    assert [item.exercise for item in body.planned_items] == ["深蹲"]
    assert [item.exercise for item in body.actual_items] == ["深蹲"]
    assert body.planned_items[0].sets == 5
    assert body.actual_items[0].sets == 4


# ---------- 空串 = 清空（不是删除）----------


def test_empty_text_clears_but_keeps_row(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """FR-8.1：已有计划日时传空串 → 文本清空，但 DayNote 行保留（不是「空串就删行」）。"""
    make.plan_day(actor_a, DAY)
    _put(client, actor_a, "先写点东西")

    body = _put(client, actor_a, "")

    assert body.note == ""
    assert body.kind == "train"  # 计划日仍在
    db_session.expire_all()
    assert _note_count(db_session) == 1
    assert _get_note(client, actor_a) == ""


def test_whitespace_only_is_treated_as_empty(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """v1 语义：先 strip 再判空，纯空白与空串同待遇。"""
    make.plan_day(actor_a, DAY)
    _put(client, actor_a, "有点累")

    body = _put(client, actor_a, "   \n  ")

    assert body.note == ""
    db_session.expire_all()
    assert _note_count(db_session) == 1


# ---------- 无 PlanDay + 空文本 = 零写入 ----------


def test_empty_text_without_plan_day_writes_nothing(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """FR-8.2：无 PlanDay 且文本为空 → 一行都不写（两个表计数都不变），返回空聚合。"""
    body = _put(client, actor_a, "")

    assert body == DayAggregate(date=DAY)
    db_session.expire_all()
    assert _plan_day_count(db_session) == 0
    assert _note_count(db_session) == 0


def test_whitespace_text_without_plan_day_writes_nothing(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """纯空白同样不建日：strip 后为空，就与空串同路。"""
    _put(client, actor_a, "    ")

    db_session.expire_all()
    assert _plan_day_count(db_session) == 0
    assert _note_count(db_session) == 0


def test_clearing_second_time_is_idempotent(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """重复清空不产生额外行（upsert 而非每次插一条）。"""
    make.plan_day(actor_a, DAY)
    _put(client, actor_a, "abc")

    _put(client, actor_a, "")
    body = _put(client, actor_a, "")

    assert body.note == ""
    db_session.expire_all()
    assert _note_count(db_session) == 1


# ---------- 契约与鉴权 ----------


def test_missing_text_is_422(client: TestClient, actor_a: Actor, db_session: Session) -> None:
    """`text` 必填：缺省 422 而不是静默当清空（PUT 是整段替换，若要清空就显式给空串）。"""
    response = client.put(f"/days/{ISO}/note", json={}, headers=actor_a.headers())
    assert response.status_code == 422

    db_session.expire_all()
    assert _plan_day_count(db_session) == 0
    assert _note_count(db_session) == 0


def test_invalid_date_is_400(client: TestClient, actor_a: Actor) -> None:
    response = client.put("/days/2026-02-30/note", json={"text": "累"}, headers=actor_a.headers())
    assert response.status_code == 400
    assert response.json() == {"detail": INVALID_DATE_DETAIL}


def test_save_note_requires_token(client: TestClient) -> None:
    assert client.put("/days/2026-01-05/note", json={"text": "累"}).status_code == 401


# ---------- 隔离 ----------


def test_other_users_same_date_gets_own_rows(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories, db_session: Session
) -> None:
    """B 写同一天不会改到 A 的行：唯一键是 (user_id, date)，各建一行。"""
    day_a = make.plan_day(actor_a, DAY)
    db_session.add(DayNote(user_id=actor_a.user_id, plan_day_id=day_a.id, text="A 的感受"))
    db_session.commit()

    body_b = _put(client, actor_b, "B 的感受")

    assert body_b.note == "B 的感受"
    assert _get_note(client, actor_a) == "A 的感受"
    db_session.expire_all()
    assert _plan_day_count(db_session) == 2
    assert _note_count(db_session) == 2


# ---------- 并发 ----------


def test_day_note_unique_race_reuses_row(
    client: TestClient,
    actor_a: Actor,
    make: Factories,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """并发首次写笔记撞 `plan_day_id` 唯一键：复用对方插的行并覆盖文本，不冒 500。"""
    day = make.plan_day(actor_a, DAY)
    db_session.add(DayNote(user_id=actor_a.user_id, plan_day_id=day.id, text="对方先写的"))
    db_session.commit()

    real = days_service._find_day_note
    state = {"raced": False}

    def first_miss(db: Session, *, user_id: int, plan_day_id: int) -> DayNote | None:
        """第一次「查不到」模拟另一会话刚插入、本会话尚未看见。"""
        if not state["raced"]:
            state["raced"] = True
            return None
        return real(db, user_id=user_id, plan_day_id=plan_day_id)

    monkeypatch.setattr(days_service, "_find_day_note", first_miss)
    body = _put(client, actor_a, "我后写的")

    assert state["raced"] is True
    assert body.note == "我后写的"
    db_session.expire_all()
    assert _note_count(db_session) == 1
