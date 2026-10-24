"""日聚合读（SRS FR-5、HLD §9.1/§9.2、§12.0「days」行）。

覆盖点（写端点随票 11/12/13 补）：
- 空日聚合初值：`kind`/`title` 为 null、两个集合为空、`note` 空串，且**不落库**（FR-5.2）；
- position 排序：计划条目与实际条目都按 `position` 升序，同 `position` 再按 id（顺序稳定）；
- 聚合内容：kind/title/note/重量组数次数/`planned_item_id` 映射；
- 隔离：B 读 A 的日期拿到空结构（不是 404 —— 读取本身合法，只是没有 B 的数据）；
- 日期非法 → **400**（不是 422，HLD §9.2）；无 token → 401。
"""

from __future__ import annotations

from datetime import date

from app.models import DayNote, PlanDay
from app.routers.days import INVALID_DATE_DETAIL
from app.schemas import ActualItemOut, DayAggregate, PlannedItemOut
from app.services import days_service
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import Actor, Factories

DAY = date(2026, 1, 5)


def _get(client: TestClient, actor: Actor, iso_date: str = "2026-01-05") -> DayAggregate:
    """按契约形状解析响应：测试断言用的是生成契约里的同一批字段名（D13）。"""
    response = client.get(f"/days/{iso_date}", headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _plan_day_count(db: Session) -> int:
    return int(db.scalar(select(func.count(PlanDay.id))) or 0)


def test_empty_day_returns_empty_aggregate_without_writing(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """FR-5.2：没有记录的日期返回空结构，且 GET 不隐式建 PlanDay。"""
    body = _get(client, actor_a)
    assert body == DayAggregate(date=DAY)
    assert body.kind is None
    assert body.title is None
    assert body.planned_items == []
    assert body.actual_items == []
    assert body.note == ""
    assert _plan_day_count(db_session) == 0


def test_aggregate_carries_plan_day_fields_and_note(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    day = make.plan_day(actor_a, DAY, kind="rest", title="上肢")
    planned = make.planned_item(
        actor_a, day, exercise="卧推", weight_kg=60.0, sets=4, reps="8-12", position=0
    )
    actual = make.actual_item(
        actor_a,
        day,
        exercise="卧推",
        planned_item=planned,
        weight_kg=62.5,
        sets=3,
        reps="10",
        note="最后一组有点抖",
        position=0,
    )
    db_session.add(DayNote(user_id=actor_a.user_id, plan_day_id=day.id, text="  累但爽  "))
    db_session.commit()

    body = _get(client, actor_a)
    assert body.kind == "rest"
    assert body.title == "上肢"
    assert body.note == "  累但爽  "
    assert body.planned_items == [
        PlannedItemOut(
            id=planned.id,
            exercise="卧推",
            weight_kg=60.0,
            sets=4,
            reps="8-12",
            position=0,
        )
    ]
    assert body.actual_items == [
        ActualItemOut(
            id=actual.id,
            planned_item_id=planned.id,
            exercise="卧推",
            weight_kg=62.5,
            sets=3,
            reps="10",
            note="最后一组有点抖",
            position=0,
        )
    ]


def test_position_orders_both_lists(client: TestClient, actor_a: Actor, make: Factories) -> None:
    """乱序插入也按 position 升序返回；同 position 用 id 兜底（顺序稳定）。"""
    day = make.plan_day(actor_a, DAY)
    make.planned_item(actor_a, day, exercise="第三个", position=2)
    make.planned_item(actor_a, day, exercise="第一个", position=0)
    make.planned_item(actor_a, day, exercise="并列A", position=1)
    make.planned_item(actor_a, day, exercise="并列B", position=1)

    make.actual_item(actor_a, day, exercise="实际第三", position=2)
    make.actual_item(actor_a, day, exercise="实际第一", position=0)
    make.actual_item(actor_a, day, exercise="实际第二", position=1)

    body = _get(client, actor_a)
    assert [item.exercise for item in body.planned_items] == ["第一个", "并列A", "并列B", "第三个"]
    assert [item.exercise for item in body.actual_items] == ["实际第一", "实际第二", "实际第三"]


def test_isolation_other_users_day_is_invisible(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories
) -> None:
    """B 读 A 的日期：不 404，但拿到的这一份里没有 A 的任何东西（FR-3）。"""
    a_day = make.plan_day(actor_a, DAY, kind="train", title="A 的腿日")
    make.planned_item(actor_a, a_day, exercise="A 深蹲", weight_kg=100.0)
    make.plan_day(actor_b, DAY, kind="rest", title="B 的休息日")

    body_b = _get(client, actor_b)
    assert body_b.kind == "rest"
    assert body_b.title == "B 的休息日"
    assert body_b.planned_items == []
    assert body_b.actual_items == []

    body_a = _get(client, actor_a)
    assert [item.exercise for item in body_a.planned_items] == ["A 深蹲"]


def test_missing_plan_day_for_other_user_stays_empty(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories
) -> None:
    """A 有记录、B 没有：B 拿到空结构，不因「A 占着这一天」而看到任何痕迹。"""
    make.plan_day(actor_a, DAY, title="只有 A")
    body_b = _get(client, actor_b)
    assert body_b.kind is None
    assert body_b.title is None
    assert body_b.planned_items == []


def test_invalid_date_is_400_not_422(client: TestClient, actor_a: Actor) -> None:
    for bad in ["2026-13-01", "2026-02-30", "not-a-date", "2026-1-5"]:
        response = client.get(f"/days/{bad}", headers=actor_a.headers())
        assert response.status_code == 400, bad
        assert response.json() == {"detail": INVALID_DATE_DETAIL}, bad


def test_day_requires_token(client: TestClient) -> None:
    assert client.get("/days/2026-01-05").status_code == 401


def test_get_or_create_plan_day_defaults_and_is_idempotent(
    db_session: Session, actor_a: Actor, actor_b: Actor
) -> None:
    """写路径的默认值：kind=train、title=None；同一天重复调用返回同一行。"""
    first = days_service.get_or_create_plan_day(db_session, user_id=actor_a.user_id, day=DAY)
    assert first.kind == "train"
    assert first.title is None
    assert first.id is not None

    again = days_service.get_or_create_plan_day(db_session, user_id=actor_a.user_id, day=DAY)
    assert again.id == first.id

    # 隔离：B 的同一天是另一行（唯一键是 (user_id, date)，不是 date）
    other = days_service.get_or_create_plan_day(db_session, user_id=actor_b.user_id, day=DAY)
    assert other.id != first.id
