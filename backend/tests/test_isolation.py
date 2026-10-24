"""归属隔离（HLD §8、§9.2、§12.0「隔离」行；SRS FR-3.1 / FR-3.2 / FR-3.4）。

本票只验地基，业务域自己的 404 断言随各自票补。覆盖点：
- 按 id 取资源：别人的 / 不存在的 → 同一 `NotFoundError`，同一 404 文案；
- 父子链不一致的脏行：对父子双方都不可见（只信子表 `user_id` 会被这种行绕过）；
- 列表查询与业务键查询：只看得见自己那一份；
- 动作库命名空间：A 的「深蹲」和 B 的「深蹲」是两条独立记录；
- HTTP 层：`NotFoundError` → 404 `{"detail": "资源不存在"}`，与真正不存在完全一致。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from typing import Annotated, Any

import pytest
from app.core.deps import get_current_user
from app.core.errors import NOT_FOUND_DETAIL, NotFoundError
from app.db import get_db
from app.models import (
    BodyMetric,
    CycleTemplate,
    Exercise,
    PlanDay,
    PlannedItem,
    TemplateItem,
    User,
)
from app.services import isolation
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from tests.conftest import Actor, Factories

DAY = date(2026, 1, 5)
MISSING_ID = 10_000_000

Resolver = Callable[..., object]

# kind → (resolver, 该 resolver 的 id 形参名)
RESOLVERS: dict[str, tuple[Resolver, str]] = {
    "planned_item": (isolation.require_planned_item, "planned_item_id"),
    "actual_item": (isolation.require_actual_item, "actual_item_id"),
    "template": (isolation.require_template, "template_id"),
    "template_day": (isolation.require_template_day, "template_day_id"),
    "template_item": (isolation.require_template_item, "template_item_id"),
}


def _owned_id(kind: str, make: Factories, actor: Actor) -> int:
    """造一件属于 actor 的资源并返回其 id（每种资源都挂在各自的最小父链上）。"""
    day = make.plan_day(actor, DAY)
    if kind == "planned_item":
        return make.planned_item(actor, day).id
    if kind == "actual_item":
        return make.actual_item(actor, day).id
    template = make.template(actor, name="循环", kinds=("train",), length_days=3)
    if kind == "template":
        return template.id
    template_day = make.template_day(actor, template)
    if kind == "template_day":
        return template_day.id
    return make.template_item(actor, template_day).id


@pytest.mark.parametrize("kind", sorted(RESOLVERS))
def test_foreign_and_missing_are_indistinguishable(
    kind: str, db_session: Session, make: Factories, actor_a: Actor, actor_b: Actor
) -> None:
    """A 的资源对 B 不可见；B 拿一个不存在的 id 得到的也是同一种失败。"""
    resolver, id_param = RESOLVERS[kind]
    resource_id = _owned_id(kind, make, actor_a)

    assert resolver(db_session, user_id=actor_a.user_id, **{id_param: resource_id}) is not None

    with pytest.raises(NotFoundError) as foreign:
        resolver(db_session, user_id=actor_b.user_id, **{id_param: resource_id})
    with pytest.raises(NotFoundError) as missing:
        resolver(db_session, user_id=actor_b.user_id, **{id_param: MISSING_ID})

    # 同一种异常、同一文案（文案只在 core/errors 产出，异常本身不带消息）
    assert str(foreign.value) == str(missing.value) == ""


def test_planned_item_with_broken_parent_chain_is_invisible_to_both(
    db_session: Session, make: Factories, actor_a: Actor, actor_b: Actor
) -> None:
    """只翻转子表冗余的 user_id（模拟脏数据 / 绕过 service 的写入）→ 谁都不能访问。"""
    day = make.plan_day(actor_a, DAY)
    item = make.planned_item(actor_a, day)
    db_session.execute(
        update(PlannedItem).where(PlannedItem.id == item.id).values(user_id=actor_b.user_id)
    )
    db_session.commit()
    db_session.expire_all()

    for actor in (actor_a, actor_b):
        with pytest.raises(NotFoundError):
            isolation.require_planned_item(
                db_session, user_id=actor.user_id, planned_item_id=item.id
            )


def test_template_item_with_broken_parent_chain_is_invisible_to_both(
    db_session: Session, make: Factories, actor_a: Actor, actor_b: Actor
) -> None:
    """两层父链都要校验：条目自称属于 B，但它挂在 A 的模板日 / 模板下。"""
    template = make.template(actor_a, name="A 的循环", kinds=("train",), length_days=3)
    template_day = make.template_day(actor_a, template)
    item = make.template_item(actor_a, template_day)
    db_session.execute(
        update(TemplateItem).where(TemplateItem.id == item.id).values(user_id=actor_b.user_id)
    )
    db_session.commit()
    db_session.expire_all()

    for actor in (actor_a, actor_b):
        with pytest.raises(NotFoundError):
            isolation.require_template_item(
                db_session, user_id=actor.user_id, template_item_id=item.id
            )


def _ids(rows: Iterable[Any]) -> set[int]:
    return {int(row.id) for row in rows}


def test_list_queries_only_see_own_rows(
    db_session: Session, make: Factories, actor_a: Actor, actor_b: Actor
) -> None:
    """日历 / 模板 / 体重 / 动作库的列表基座：A 与 B 各看各的。"""
    a_day = make.plan_day(actor_a, DAY, title="腿")
    a_item = make.planned_item(actor_a, a_day, exercise="深蹲")
    a_template = make.template(actor_a, name="A 循环")
    a_metric = make.body_metric(actor_a, DAY, 82.5)
    a_exercise = make.exercise(actor_a, "深蹲")

    b_day = make.plan_day(actor_b, DAY, title="胸")
    b_item = make.planned_item(actor_b, b_day, exercise="卧推")
    b_template = make.template(actor_b, name="B 循环", kinds=("rest",))
    b_metric = make.body_metric(actor_b, DAY, 70.0)
    b_exercise = make.exercise(actor_b, "卧推")

    def owned_ids(model: Any, actor: Actor) -> set[int]:
        return _ids(db_session.scalars(isolation.select_owned(model, actor.user_id)))

    assert owned_ids(PlanDay, actor_a) == {a_day.id}
    assert owned_ids(PlanDay, actor_b) == {b_day.id}
    assert owned_ids(PlannedItem, actor_a) == {a_item.id}
    assert owned_ids(PlannedItem, actor_b) == {b_item.id}
    assert owned_ids(CycleTemplate, actor_a) == {a_template.id}
    assert owned_ids(CycleTemplate, actor_b) == {b_template.id}
    assert owned_ids(BodyMetric, actor_a) == {a_metric.id}
    assert owned_ids(BodyMetric, actor_b) == {b_metric.id}
    assert owned_ids(Exercise, actor_a) == {a_exercise.id}
    assert owned_ids(Exercise, actor_b) == {b_exercise.id}


def test_business_key_lookups_are_scoped(
    db_session: Session, make: Factories, actor_a: Actor, actor_b: Actor
) -> None:
    """同一天 / 同一周在 A、B 各自的命名空间里互不干扰。"""
    a_day = make.plan_day(actor_a, DAY)
    a_metric = make.body_metric(actor_a, DAY, 82.5)

    assert isolation.find_plan_day(db_session, user_id=actor_a.user_id, day=DAY) is a_day
    assert isolation.find_plan_day(db_session, user_id=actor_b.user_id, day=DAY) is None
    assert (
        isolation.find_body_metric(db_session, user_id=actor_a.user_id, week_start=DAY) is a_metric
    )
    assert isolation.find_body_metric(db_session, user_id=actor_b.user_id, week_start=DAY) is None


def test_exercise_namespace_is_isolated(
    db_session: Session, make: Factories, actor_a: Actor, actor_b: Actor
) -> None:
    """A 的「深蹲」对 B 不可见，B 可以有自己的同名动作（SRS FR-3.4）。"""
    a_squat = make.exercise(actor_a, "深蹲")
    b_squat = make.exercise(actor_b, "深蹲")

    assert a_squat.id != b_squat.id
    assert isolation.find_exercise(db_session, user_id=actor_a.user_id, name="深蹲") is a_squat
    assert isolation.find_exercise(db_session, user_id=actor_b.user_id, name="深蹲") is b_squat
    assert isolation.find_exercise(db_session, user_id=actor_b.user_id, name="硬拉") is None

    # 重复取同名不新增（(user_id, name) 命名空间内幂等）
    assert make.exercise(actor_a, "深蹲") is a_squat


@pytest.fixture()
def probe_client(client: TestClient, app: FastAPI) -> TestClient:
    """在已启动的 app 上挂一个只做归属校验的探针端点（业务路由随各自票落地）。"""

    def _planned_item(
        planned_item_id: int,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> dict[str, int]:
        item = isolation.require_planned_item(db, user_id=user.id, planned_item_id=planned_item_id)
        return {"id": item.id}

    app.router.add_api_route(
        "/_test/planned-item/{planned_item_id}",
        _planned_item,
        methods=["GET"],
        include_in_schema=False,
    )
    return client


def test_http_404_body_is_uniform(
    probe_client: TestClient, make: Factories, actor_a: Actor, actor_b: Actor
) -> None:
    """别人的资源与不存在的资源，HTTP 响应完全一致（防枚举，HLD §9.2）。"""
    day = make.plan_day(actor_a, DAY)
    item = make.planned_item(actor_a, day)

    own = probe_client.get(f"/_test/planned-item/{item.id}", headers=actor_a.headers())
    assert own.status_code == 200
    assert own.json() == {"id": item.id}

    foreign = probe_client.get(f"/_test/planned-item/{item.id}", headers=actor_b.headers())
    missing = probe_client.get(f"/_test/planned-item/{MISSING_ID}", headers=actor_b.headers())

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": NOT_FOUND_DETAIL}


def test_http_401_comes_before_any_404(
    probe_client: TestClient, make: Factories, actor_a: Actor
) -> None:
    """隔离不是鉴权的替代品：没有 token 先 401，轮不到 404。"""
    day = make.plan_day(actor_a, DAY)
    item = make.planned_item(actor_a, day)

    assert probe_client.get(f"/_test/planned-item/{item.id}").status_code == 401
