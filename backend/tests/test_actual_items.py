"""实际完成记录（SRS FR-7、HLD §9.1/§9.2、§12.0「days」行）。

覆盖点：
- prefill（FR-7.1）：按计划复制**当前计划值**并带 `planned_item_id`、置于末尾；连调两次条数不变
  （幂等）；只补还没有对应实际条目的计划条目；当天无 PlanDay 时静默 no-op（**不隐式建日**）；
  非法日期 400；只碰自己的数据；
- 行内更新（FR-7.2）：三态语义 —— 字段缺省不动 / 显式 `null` 置空 / 空串置空；解析失败置空而非
  422；空 body 是合法 no-op；
- 计划外新增（FR-7.3）：`planned_item_id` 为 null、隐式建日为 train、备注 trim 后空则 NULL、
  空动作名 422 且不落库；prefill 之后再新增仍落末位；
- 删除（FR-7.4）：直接删、剩余 position 重排连续（删后新增不撞号）；
- 隔离：B 对 A 的条目 PATCH/DELETE 一律 404 且同码同文案（FR-3.2）；无 token 401；
- 并发：prefill 撞 UNIQUE(plan_day_id, planned_item_id) 时整批回滚重算，不冒 500。
"""

from __future__ import annotations

from datetime import date

import pytest
from app.core.errors import NOT_FOUND_DETAIL
from app.models import ActualItem, Exercise, PlanDay
from app.routers.days import INVALID_DATE_DETAIL
from app.schemas import ActualItemUpdate, DayAggregate
from app.services import days_service
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import Actor, Factories

DAY = date(2026, 1, 5)
ISO = "2026-01-05"


def _prefill(client: TestClient, actor: Actor, iso_date: str = ISO) -> DayAggregate:
    response = client.post(f"/days/{iso_date}/actual/prefill", headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _create(
    client: TestClient,
    actor: Actor,
    *,
    exercise: str = "引体向上",
    iso_date: str = ISO,
    **fields: str | None,
) -> DayAggregate:
    payload: dict[str, str | None] = {"exercise": exercise, **fields}
    response = client.post(f"/days/{iso_date}/actual-items", json=payload, headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _patch(
    client: TestClient, actor: Actor, item_id: int, payload: dict[str, str | None]
) -> DayAggregate:
    response = client.patch(f"/actual-items/{item_id}", json=payload, headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _delete(client: TestClient, actor: Actor, item_id: int) -> DayAggregate:
    response = client.delete(f"/actual-items/{item_id}", headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _seed_actual(actor: Actor, make: Factories) -> ActualItem:
    """一条「已经练完」的实际条目：四列都有值，便于验证「只改给了的字段」。"""
    day = make.plan_day(actor, DAY)
    return make.actual_item(
        actor, day, exercise="深蹲", weight_kg=60.0, sets=4, reps="8-12", note="原文"
    )


def _actual_count(db: Session) -> int:
    return int(db.scalar(select(func.count(ActualItem.id))) or 0)


def _plan_day_count(db: Session) -> int:
    return int(db.scalar(select(func.count(PlanDay.id))) or 0)


# ---------- prefill ----------


def test_prefill_copies_plan_values_and_links(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """FR-7.1：复制当前计划值（不是模板），带 planned_item_id，按计划顺序置末位。"""
    day = make.plan_day(actor_a, DAY, title="下肢")
    heavy = make.planned_item(actor_a, day, exercise="深蹲", weight_kg=100.0, sets=5, reps="5")
    bare = make.planned_item(actor_a, day, exercise="腿弯举")

    body = _prefill(client, actor_a)

    assert body.kind == "train"
    assert body.title == "下肢"
    assert [item.exercise for item in body.actual_items] == ["深蹲", "腿弯举"]
    assert [item.position for item in body.actual_items] == [0, 1]
    assert [item.planned_item_id for item in body.actual_items] == [heavy.id, bare.id]

    first, second = body.actual_items
    assert (first.weight_kg, first.sets, first.reps, first.note) == (100.0, 5, "5", None)
    assert (second.weight_kg, second.sets, second.reps) == (None, None, None)
    # 计划条目本身不动
    assert [item.id for item in body.planned_items] == [heavy.id, bare.id]


def test_prefill_is_idempotent(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """连调两次条数不变、id 不变（UNIQUE(plan_day_id, planned_item_id) + 「先查再补」双保险）。"""
    day = make.plan_day(actor_a, DAY)
    make.planned_item(actor_a, day, exercise="深蹲")
    make.planned_item(actor_a, day, exercise="卧推")

    first = _prefill(client, actor_a)
    second = _prefill(client, actor_a)

    assert len(first.actual_items) == 2
    assert second.actual_items == first.actual_items
    db_session.expire_all()
    assert _actual_count(db_session) == 2


def test_prefill_only_fills_missing_and_appends(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """已经练过的行不覆盖（哪怕计划值改过），缺的行追加在末尾。"""
    day = make.plan_day(actor_a, DAY)
    planned_squat = make.planned_item(actor_a, day, exercise="深蹲", sets=5)
    planned_bench = make.planned_item(actor_a, day, exercise="卧推", sets=3)
    done = make.actual_item(
        actor_a, day, exercise="深蹲", planned_item=planned_squat, sets=1, note="只练了一组"
    )

    body = _prefill(client, actor_a)

    assert [item.id for item in body.actual_items] == [done.id, body.actual_items[1].id]
    assert [item.position for item in body.actual_items] == [0, 1]
    kept = body.actual_items[0]
    assert (kept.sets, kept.note) == (1, "只练了一组")  # 实际值不被计划值覆盖
    appended = body.actual_items[1]
    assert (appended.planned_item_id, appended.exercise, appended.sets) == (
        planned_bench.id,
        "卧推",
        3,
    )


def test_prefill_without_plan_day_is_noop(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """当天没有 PlanDay 时静默 no-op：空聚合，且不隐式建日（prefill 是「照计划复制」）。"""
    body = _prefill(client, actor_a)

    assert body == DayAggregate(date=DAY)
    db_session.expire_all()
    assert _plan_day_count(db_session) == 0
    assert _actual_count(db_session) == 0
    assert int(db_session.scalar(select(func.count(Exercise.id))) or 0) == 0


def test_prefill_invalid_date_is_400(client: TestClient, actor_a: Actor) -> None:
    response = client.post("/days/2026-02-30/actual/prefill", headers=actor_a.headers())
    assert response.status_code == 400
    assert response.json() == {"detail": INVALID_DATE_DETAIL}


def test_prefill_requires_token(client: TestClient) -> None:
    assert client.post("/days/2026-01-05/actual/prefill").status_code == 401


def test_prefill_is_scoped_per_user(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories
) -> None:
    """B 的 prefill 看不见 A 的计划日：B 得到空聚合，A 的条目一条也没多出来。"""
    day_a = make.plan_day(actor_a, DAY)
    make.planned_item(actor_a, day_a, exercise="A 深蹲")

    assert _prefill(client, actor_b).actual_items == []
    body_a = _prefill(client, actor_a)
    assert [item.exercise for item in body_a.actual_items] == ["A 深蹲"]


# ---------- 行内更新三态（FR-7.2）----------


def test_patch_missing_field_is_left_untouched(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """只给 weight：其余三列原封不动（不能因为 payload 里默认 None 就清空）。"""
    item = _seed_actual(actor_a, make)

    updated = _patch(client, actor_a, item.id, {"weight": "70kg"}).actual_items[0]

    assert (updated.weight_kg, updated.sets, updated.reps, updated.note) == (
        70.0,
        4,
        "8-12",
        "原文",
    )


def test_patch_explicit_null_clears_fields(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """显式 null 也是「置空」一态：按值分不出来，只能靠 model_fields_set。"""
    item = _seed_actual(actor_a, make)

    updated = _patch(client, actor_a, item.id, {"weight": None, "note": None}).actual_items[0]

    assert updated.weight_kg is None
    assert updated.note is None
    assert (updated.sets, updated.reps) == (4, "8-12")


def test_patch_empty_string_clears_fields(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """FR-7.2：空串含义为置 NULL / 空（reps 是自由文本，落空串而非 NULL）。"""
    item = _seed_actual(actor_a, make)

    updated = _patch(
        client, actor_a, item.id, {"weight": "", "sets": "", "reps": "", "note": ""}
    ).actual_items[0]

    assert updated.weight_kg is None
    assert updated.sets is None
    assert updated.reps == ""
    assert updated.note is None


def test_patch_parses_dose_and_keeps_free_text(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """重量逗号小数点 / 单位剥除照 parsing 语义；次数是自由文本；解析不出来就置空（不 422）。"""
    item = _seed_actual(actor_a, make)

    body = _patch(client, actor_a, item.id, {"sets": "5", "reps": " 12/12/10 "})
    assert (body.actual_items[0].sets, body.actual_items[0].reps) == (5, "12/12/10")

    parsed = _patch(client, actor_a, item.id, {"weight": "62,5kg"})
    assert parsed.actual_items[0].weight_kg == 62.5

    garbage = _patch(client, actor_a, item.id, {"weight": "abc"})
    assert garbage.actual_items[0].weight_kg is None
    assert garbage.actual_items[0].sets == 5  # 同一行的其他列不受影响


def test_patch_empty_body_is_noop(client: TestClient, actor_a: Actor, make: Factories) -> None:
    """空对象合法：一列都不改，仍返回新鲜聚合。"""
    item = _seed_actual(actor_a, make)

    updated = _patch(client, actor_a, item.id, {}).actual_items[0]

    assert (updated.weight_kg, updated.sets, updated.reps, updated.note) == (
        60.0,
        4,
        "8-12",
        "原文",
    )


def test_patch_missing_item_is_404(client: TestClient, actor_a: Actor) -> None:
    response = client.patch("/actual-items/9999", json={"weight": "60"}, headers=actor_a.headers())
    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_patch_field_map_covers_exact_columns() -> None:
    """不变量：可更新字段的四个契约名都映射到 `actual_item` 的真实列。

    `setattr(item, "weight", ...)` 不会报错，只会写到一个非映射属性上（响应里仍是旧值）——
    这条测试是那种静默失效的通用拦截：列名写错 / 字段漏加都在这里炸。
    """
    from app.services.days_service import _ACTUAL_FIELD_UPDATES

    assert set(_ACTUAL_FIELD_UPDATES) == set(ActualItemUpdate.model_fields)
    for column, _parse in _ACTUAL_FIELD_UPDATES.values():
        assert column in ActualItem.__table__.columns


# ---------- 计划外新增（FR-7.3）----------


def test_create_planned_outside_item(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """计划外条目：planned_item_id 为 null、隐式建 train 日、备注 trim、重量解析不出存 NULL。"""
    body = _create(
        client,
        actor_a,
        exercise=" 引体向上 ",
        weight="自重",
        sets="3",
        reps="8",
        note="  补两组  ",
    )

    assert body.kind == "train"
    assert body.title is None
    item = body.actual_items[0]
    assert item.planned_item_id is None
    assert item.exercise == "引体向上"
    assert (item.weight_kg, item.sets, item.reps, item.note) == (None, 3, "8", "补两组")
    assert item.position == 0

    db_session.expire_all()
    assert db_session.scalars(
        select(Exercise.name).where(Exercise.user_id == actor_a.user_id)
    ).all() == ["引体向上"]


def test_create_blank_note_is_null(client: TestClient, actor_a: Actor) -> None:
    """备注只给空白字符 = 未填（v1 `(note or "").strip() or None` 同义）。"""
    item = _create(client, actor_a, note="   ").actual_items[0]
    assert item.note is None


def test_create_after_prefill_appends_to_end(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """prefill 与新增共用同一个 position 计数：新增仍落在末尾，不与预填行撞号。"""
    day = make.plan_day(actor_a, DAY)
    make.planned_item(actor_a, day, exercise="深蹲")
    _prefill(client, actor_a)

    body = _create(client, actor_a, exercise="引体向上")

    assert [item.exercise for item in body.actual_items] == ["深蹲", "引体向上"]
    assert [item.position for item in body.actual_items] == [0, 1]


def test_create_empty_exercise_is_422(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    for payload in ({"exercise": ""}, {"exercise": "   "}):
        response = client.post(f"/days/{ISO}/actual-items", json=payload, headers=actor_a.headers())
        assert response.status_code == 422, payload

    db_session.expire_all()
    assert _actual_count(db_session) == 0
    assert _plan_day_count(db_session) == 0


def test_create_invalid_date_is_400(client: TestClient, actor_a: Actor) -> None:
    response = client.post(
        "/days/2026-13-01/actual-items", json={"exercise": "深蹲"}, headers=actor_a.headers()
    )
    assert response.status_code == 400
    assert response.json() == {"detail": INVALID_DATE_DETAIL}


def test_create_requires_token(client: TestClient) -> None:
    response = client.post("/days/2026-01-05/actual-items", json={"exercise": "深蹲"})
    assert response.status_code == 401


# ---------- 删除（FR-7.4）----------


def test_delete_renumbers_remaining_positions(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """删中间一条：剩余 position 连续 0..n-1，接着新增仍落末位（不会撞号留洞）。"""
    day = make.plan_day(actor_a, DAY)
    first, second, third = (
        make.actual_item(actor_a, day, exercise=name).id for name in ("动作A", "动作B", "动作C")
    )

    body = _delete(client, actor_a, second)
    assert [item.exercise for item in body.actual_items] == ["动作A", "动作C"]
    assert [item.position for item in body.actual_items] == [0, 1]
    assert [item.id for item in body.actual_items] == [first, third]

    appended = _create(client, actor_a, exercise="动作D")
    assert [item.position for item in appended.actual_items] == [0, 1, 2]
    db_session.expire_all()
    assert _actual_count(db_session) == 3


def test_delete_missing_item_is_404(client: TestClient, actor_a: Actor) -> None:
    response = client.delete("/actual-items/9999", headers=actor_a.headers())
    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_delete_requires_token(client: TestClient) -> None:
    assert client.delete("/actual-items/1").status_code == 401


# ---------- 隔离 ----------


def test_other_users_actual_item_is_404_for_update_and_delete(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories, db_session: Session
) -> None:
    """B patch / delete A 的条目：404 且与「不存在」同码同文案，A 的数据毫发无损。"""
    item = _seed_actual(actor_a, make)

    for response in (
        client.patch(f"/actual-items/{item.id}", json={"weight": "1"}, headers=actor_b.headers()),
        client.delete(f"/actual-items/{item.id}", headers=actor_b.headers()),
    ):
        assert response.status_code == 404
        assert response.json() == {"detail": NOT_FOUND_DETAIL}

    db_session.expire_all()
    assert _actual_count(db_session) == 1
    survived = db_session.get(ActualItem, item.id)
    assert survived is not None
    assert (survived.weight_kg, survived.sets) == (60.0, 4)


def test_same_date_is_separate_per_user(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories
) -> None:
    """同一日期两人各自建实际条目，互不可见也互不覆盖。"""
    item_a = _seed_actual(actor_a, make)

    body_b = _create(client, actor_b, exercise="B 卧推", sets="3")
    assert [item.exercise for item in body_b.actual_items] == ["B 卧推"]
    assert [item.position for item in body_b.actual_items] == [0]

    body_a = _patch(client, actor_a, item_a.id, {"sets": "6"})
    assert [item.exercise for item in body_a.actual_items] == ["深蹲"]
    assert body_a.actual_items[0].sets == 6


# ---------- 并发 prefill ----------


def test_prefill_unique_race_recomputes(
    client: TestClient,
    actor_a: Actor,
    make: Factories,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """另一会话刚补上同一计划条目的实际行：撞唯一键后整批回滚重算，补完剩下的，不冒 500。"""
    day = make.plan_day(actor_a, DAY)
    squat = make.planned_item(actor_a, day, exercise="深蹲")
    bench = make.planned_item(actor_a, day, exercise="卧推")
    make.actual_item(actor_a, day, exercise="深蹲", planned_item=squat)

    real = days_service._linked_planned_item_ids
    state = {"raced": False}

    def first_miss(db: Session, *, user_id: int, plan_day_id: int) -> set[int]:
        """第一次「查不到已补条目」模拟并发请求尚未提交的行，之后恢复真实查询。"""
        if not state["raced"]:
            state["raced"] = True
            return set()
        return real(db, user_id=user_id, plan_day_id=plan_day_id)

    monkeypatch.setattr(days_service, "_linked_planned_item_ids", first_miss)
    body = _prefill(client, actor_a)

    assert state["raced"] is True
    assert [item.planned_item_id for item in body.actual_items] == [squat.id, bench.id]
    db_session.expire_all()
    assert _actual_count(db_session) == 2
