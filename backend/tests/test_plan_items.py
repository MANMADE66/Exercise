"""计划条目增删移（SRS FR-6、HLD §9.1/§9.2、§12.0「days」行）。

覆盖点：
- 添加：置于末位、动作名自动建入本人动作库、重量/组数容错解析（失败存 NULL 不报错）、
  次数保留原文本、空动作名 422、非法日期 400、隐式建日（kind=train / title=None）；
- 删除：返回聚合、剩余条目 position 重排连续、关联实际条目保留且 `planned_item_id` 置空；
- 上下移：交换后全组重排（含脏库里重复 position 的情形）、边界静默成功、direction 非法 422；
- 隔离：B 增删移 A 的条目一律 404 且同码同文案；无 token 401；
- 并发：`get_or_create` 撞唯一键（动作名 / 计划日）时回滚重查复用，不冒 500。
"""

from __future__ import annotations

from datetime import date

import pytest
from app.core.errors import NOT_FOUND_DETAIL
from app.models import Exercise, PlanDay, PlannedItem
from app.routers.days import INVALID_DATE_DETAIL
from app.schemas import DayAggregate, PlannedItemOut
from app.services import days_service, isolation
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import Actor, Factories

DAY = date(2026, 1, 5)
ISO = "2026-01-05"


def _add(
    client: TestClient,
    actor: Actor,
    *,
    exercise: str = "深蹲",
    weight: str | None = None,
    sets: str | None = None,
    reps: str | None = None,
    iso_date: str = ISO,
) -> DayAggregate:
    payload: dict[str, str] = {"exercise": exercise}
    for key, value in (("weight", weight), ("sets", sets), ("reps", reps)):
        if value is not None:
            payload[key] = value
    response = client.post(f"/days/{iso_date}/plan-items", json=payload, headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _delete(client: TestClient, actor: Actor, item_id: int) -> DayAggregate:
    response = client.delete(f"/plan-items/{item_id}", headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _move(client: TestClient, actor: Actor, item_id: int, direction: str) -> DayAggregate:
    response = client.post(
        f"/plan-items/{item_id}/move", json={"direction": direction}, headers=actor.headers()
    )
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _add_three(client: TestClient, actor: Actor) -> list[int]:
    """造 A/B/C 三条（position 0/1/2），返回 id 顺序。"""
    return [
        _add(client, actor, exercise=name).planned_items[-1].id
        for name in ("动作A", "动作B", "动作C")
    ]


def _item_count(db: Session) -> int:
    return int(db.scalar(select(func.count(PlannedItem.id))) or 0)


def _exercise_count(db: Session) -> int:
    return int(db.scalar(select(func.count(Exercise.id))) or 0)


# ---------- 添加 ----------


def test_add_appends_to_end_and_creates_plan_day(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """FR-6.1：首条 position=0，第二条 position=1（末位）；隐式建日为 train 且无标题。"""
    db_session.expire_all()
    first = _add(client, actor_a, exercise="深蹲")
    assert first.kind == "train"
    assert first.title is None
    assert [item.position for item in first.planned_items] == [0]
    assert first.planned_items[0].exercise == "深蹲"

    second = _add(client, actor_a, exercise="卧推")
    assert [item.exercise for item in second.planned_items] == ["深蹲", "卧推"]
    assert [item.position for item in second.planned_items] == [0, 1]

    # 动作名自动建入本人动作库
    db_session.expire_all()
    names = db_session.scalars(
        select(Exercise.name).where(Exercise.user_id == actor_a.user_id).order_by(Exercise.id)
    ).all()
    assert list(names) == ["深蹲", "卧推"]


def test_add_parses_dose_without_raising(client: TestClient, actor_a: Actor) -> None:
    """FR-6.4：60kg→60、逗号当小数点；解析失败的重量/组数存 NULL 而不是 422；次数原样 trim。"""
    body = _add(client, actor_a, exercise="深蹲", weight="60kg", sets="4", reps=" 8-12 ")
    item = body.planned_items[0]
    assert (item.weight_kg, item.sets, item.reps) == (60.0, 4, "8-12")

    garbage = _add(client, actor_a, exercise="卧推", weight="abc", sets="0", reps="")
    bad = garbage.planned_items[-1]
    assert bad.weight_kg is None
    assert bad.sets is None
    assert bad.reps == ""  # v1 语义：次数是自由文本，空就是空串（不是 NULL）

    comma = _add(client, actor_a, exercise="硬拉", weight="62,5")
    assert comma.planned_items[-1].weight_kg == 62.5


def test_add_empty_exercise_is_422(client: TestClient, actor_a: Actor, db_session: Session) -> None:
    """空动作名不静默吞掉（v1 是 no-op）：422 且一行都不落库。"""
    for payload in ({"exercise": ""}, {"exercise": "   "}):
        response = client.post(f"/days/{ISO}/plan-items", json=payload, headers=actor_a.headers())
        assert response.status_code == 422, payload

    db_session.expire_all()
    assert _item_count(db_session) == 0
    assert int(db_session.scalar(select(func.count(PlanDay.id))) or 0) == 0


def test_add_reuses_exercise_row_for_same_name(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """同名动作复用同一行（(user_id, name) 唯一），不因添加两次多出一条动作。"""
    first = _add(client, actor_a, exercise="深蹲")
    second = _add(client, actor_a, exercise="深蹲")
    assert [item.id for item in first.planned_items] == [second.planned_items[0].id]

    db_session.expire_all()
    assert _exercise_count(db_session) == 1
    assert _item_count(db_session) == 2


def test_add_invalid_date_is_400(client: TestClient, actor_a: Actor) -> None:
    response = client.post(
        "/days/2026-02-30/plan-items", json={"exercise": "深蹲"}, headers=actor_a.headers()
    )
    assert response.status_code == 400
    assert response.json() == {"detail": INVALID_DATE_DETAIL}


def test_add_requires_token(client: TestClient) -> None:
    assert client.post("/days/2026-01-05/plan-items", json={"exercise": "深蹲"}).status_code == 401


# ---------- 删除 ----------


def test_delete_keeps_actual_item_and_nulls_link(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """FR-6.2：删计划条目不动实际条目，只把 `planned_item_id` 置空（历史保留）。"""
    day = make.plan_day(actor_a, DAY)
    planned = make.planned_item(actor_a, day, exercise="深蹲", weight_kg=100.0)
    actual = make.actual_item(actor_a, day, exercise="深蹲", planned_item=planned, sets=3)
    planned_id, actual_id = planned.id, actual.id

    body = _delete(client, actor_a, planned_id)
    assert body.planned_items == []
    assert len(body.actual_items) == 1
    assert body.actual_items[0].id == actual_id
    assert body.actual_items[0].planned_item_id is None

    db_session.expire_all()
    assert _item_count(db_session) == 0
    assert db_session.get(PlannedItem, planned_id) is None


def test_delete_renumbers_remaining_positions(client: TestClient, actor_a: Actor) -> None:
    """删掉中间一条后剩余 position 连续 0..n-1，接着添加仍落在末位（不会撞号）。"""
    first, second, third = _add_three(client, actor_a)

    body = _delete(client, actor_a, second)
    assert [item.exercise for item in body.planned_items] == ["动作A", "动作C"]
    assert [item.position for item in body.planned_items] == [0, 1]

    appended = _add(client, actor_a, exercise="动作D")
    assert [item.exercise for item in appended.planned_items] == ["动作A", "动作C", "动作D"]
    assert [item.position for item in appended.planned_items] == [0, 1, 2]
    assert {first, third}.issubset({item.id for item in appended.planned_items})


def test_delete_missing_item_is_404(client: TestClient, actor_a: Actor) -> None:
    response = client.delete("/plan-items/9999", headers=actor_a.headers())
    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


# ---------- 上下移 ----------


def test_move_swaps_and_renumbers(client: TestClient, actor_a: Actor) -> None:
    """FR-6.3：相邻交换后全组 position 重排为 0..n-1。"""
    first, _, third = _add_three(client, actor_a)

    moved_up = _move(client, actor_a, third, "up")
    assert [item.exercise for item in moved_up.planned_items] == ["动作A", "动作C", "动作B"]
    assert [item.position for item in moved_up.planned_items] == [0, 1, 2]

    moved_down = _move(client, actor_a, first, "down")
    assert [item.exercise for item in moved_down.planned_items] == ["动作C", "动作A", "动作B"]
    assert [item.position for item in moved_down.planned_items] == [0, 1, 2]

    detailed = moved_down.planned_items[1]
    assert detailed == PlannedItemOut(
        id=first,
        exercise="动作A",
        weight_kg=None,
        sets=None,
        reps="",
        position=1,
    )


def test_move_renumbers_dirty_duplicate_positions(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """脏库里三条 position 都是 0：移动后必须重排成 0/1/2，而不是只换两个值留下重复。"""
    day = make.plan_day(actor_a, DAY)
    ids = [
        make.planned_item(actor_a, day, exercise=name, position=0).id
        for name in ("动作A", "动作B", "动作C")
    ]

    body = _move(client, actor_a, ids[0], "down")
    assert [item.position for item in body.planned_items] == [0, 1, 2]
    assert [item.exercise for item in body.planned_items] == ["动作B", "动作A", "动作C"]


def test_move_at_boundary_is_silent_success(client: TestClient, actor_a: Actor) -> None:
    """边界（首个上移 / 末个下移）静默成功：200 + 顺序不变，不 4xx。"""
    first, second, third = _add_three(client, actor_a)

    for item_id, direction in ((first, "up"), (third, "down")):
        body = _move(client, actor_a, item_id, direction)
        assert [item.exercise for item in body.planned_items] == ["动作A", "动作B", "动作C"]
        assert [item.position for item in body.planned_items] == [0, 1, 2]
        assert [item.id for item in body.planned_items] == [first, second, third]

    # 只有一条时两个方向也都静默成功
    solo_client_owner = _add(client, actor_a, iso_date="2026-02-02")
    solo_id = solo_client_owner.planned_items[0].id
    for direction in ("up", "down"):
        response = client.post(
            f"/plan-items/{solo_id}/move", json={"direction": direction}, headers=actor_a.headers()
        )
        assert response.status_code == 200, direction


def test_move_invalid_direction_is_422(client: TestClient, actor_a: Actor) -> None:
    item_id = _add_three(client, actor_a)[0]
    response = client.post(
        f"/plan-items/{item_id}/move", json={"direction": "left"}, headers=actor_a.headers()
    )
    assert response.status_code == 422


def test_move_missing_item_is_404(client: TestClient, actor_a: Actor) -> None:
    response = client.post(
        "/plan-items/9999/move", json={"direction": "up"}, headers=actor_a.headers()
    )
    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


# ---------- 隔离 ----------


def test_other_users_item_is_404_for_every_write(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories, db_session: Session
) -> None:
    """B 删 / 移 A 的条目：404，且与「不存在」同码同文案（FR-3.2），A 的数据毫发无损。"""
    day = make.plan_day(actor_a, DAY)
    planned = make.planned_item(actor_a, day, exercise="A 深蹲", position=0)
    make.planned_item(actor_a, day, exercise="A 卧推", position=1)

    for response in (
        client.delete(f"/plan-items/{planned.id}", headers=actor_b.headers()),
        client.post(
            f"/plan-items/{planned.id}/move", json={"direction": "down"}, headers=actor_b.headers()
        ),
    ):
        assert response.status_code == 404
        assert response.json() == {"detail": NOT_FOUND_DETAIL}

    db_session.expire_all()
    assert _item_count(db_session) == 2
    assert db_session.get(PlannedItem, planned.id) is not None


def test_same_date_is_separate_per_user(client: TestClient, actor_a: Actor, actor_b: Actor) -> None:
    """同名日期两个用户各有自己的计划日与条目，互不可见也不撞唯一键。"""
    _add(client, actor_a, exercise="A 深蹲")
    body_b = _add(client, actor_b, exercise="B 卧推")
    assert [item.exercise for item in body_b.planned_items] == ["B 卧推"]
    assert [item.position for item in body_b.planned_items] == [0]


# ---------- 并发 get-or-create ----------


def test_plan_day_unique_race_reuses_existing_row(
    db_session: Session, actor_a: Actor, make: Factories, monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发建日撞 (user_id, date)：回滚这一条后重查复用，不冒 500（票 09 留下的欠账）。"""
    existing = make.plan_day(actor_a, DAY)
    real = isolation.find_plan_day
    state = {"raced": False}

    def first_miss(db: Session, *, user_id: int, day: date) -> PlanDay | None:
        """第一次「查不到」模拟另一会话刚抢建，之后恢复真实查询。"""
        if not state["raced"]:
            state["raced"] = True
            return None
        return real(db, user_id=user_id, day=day)

    monkeypatch.setattr(days_service, "find_plan_day", first_miss)
    found = days_service.get_or_create_plan_day(db_session, user_id=actor_a.user_id, day=DAY)

    assert state["raced"] is True
    assert found.id == existing.id
    db_session.expire_all()
    assert int(db_session.scalar(select(func.count(PlanDay.id))) or 0) == 1
    assert _item_count(db_session) == 0


def test_exercise_unique_race_reuses_existing_row(
    db_session: Session, actor_a: Actor, make: Factories, monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发建动作撞 (user_id, name)：同样复用既有行，且计划日不被连坐回滚。"""
    make.exercise(actor_a, name="深蹲")
    real = isolation.find_exercise
    state = {"raced": False}

    def first_miss(db: Session, *, user_id: int, name: str) -> Exercise | None:
        if not state["raced"]:
            state["raced"] = True
            return None
        return real(db, user_id=user_id, name=name)

    monkeypatch.setattr(days_service, "find_exercise", first_miss)
    body = days_service.add_planned_item(
        db_session, user_id=actor_a.user_id, day=DAY, exercise="深蹲", weight="100", sets="5"
    )

    assert state["raced"] is True
    assert [item.exercise for item in body.planned_items] == ["深蹲"]
    assert body.planned_items[0].weight_kg == 100.0
    db_session.expire_all()
    assert _exercise_count(db_session) == 1
    assert _item_count(db_session) == 1
