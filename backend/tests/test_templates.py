"""循环模板（SRS FR-9、HLD §9.1/§9.2、§12.0「templates」行；v1 `app/cycle.py` 语义）。

覆盖点：
- 创建：名称 strip / 空名落「未命名循环」；天数非法回退 8、超界静默截断 12、`days` 多出的天被忽略、
  不足的补默认训练日；kind 非 `rest` 一律 train（不 422）；title 空即 NULL；空动作名忽略、
  position 从 0 递增；模板不含重量（`weight_kg`/`sets`/`reps` 全 NULL）；
- 列表：按模板 id 升序、逐日按 `day_index`、条目按 `position`；A/B 互不可见；
- 删除：级联天与条目、返回剩余列表；跨用户 / 不存在一律 404 且同码同文案；
- apply：从 `start` 按 `day_index` 铺排；**已有 PlanDay 的日期跳过且不覆盖**（断言原 title 与
  原计划条目未变、模板条目没被塞进去）；`created`/`skipped`/`skipped_dates` 计数；重复 apply 幂等
  （全跳过）；B 的同日 PlanDay 不阻挡 A；跨用户模板 404；`start` 非法 400（不是 422）；跨用户
  日期不受影响；
- 脏行：条目指向别人动作库时对当前用户不可见，apply 也不抄。
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.errors import NOT_FOUND_DETAIL
from app.models import Exercise, PlanDay, TemplateDay, TemplateItem
from app.routers.days import INVALID_DATE_DETAIL
from app.schemas import DayAggregate, TemplateAggregate, TemplateApplyResult
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import Actor, Factories

START = date(2026, 3, 1)
START_ISO = "2026-03-01"


# ---------- 助手 ----------


def _create(client: TestClient, actor: Actor, payload: dict[str, object]) -> TemplateAggregate:
    response = client.post("/templates", json=payload, headers=actor.headers())
    assert response.status_code == 200, response.text
    return TemplateAggregate.model_validate(response.json())


def _list(client: TestClient, actor: Actor) -> list[TemplateAggregate]:
    response = client.get("/templates", headers=actor.headers())
    assert response.status_code == 200, response.text
    return [TemplateAggregate.model_validate(item) for item in response.json()]


def _apply(client: TestClient, actor: Actor, template_id: int, start: str) -> TemplateApplyResult:
    response = client.post(
        f"/templates/{template_id}/apply", json={"start": start}, headers=actor.headers()
    )
    assert response.status_code == 200, response.text
    return TemplateApplyResult.model_validate(response.json())


def _delete(client: TestClient, actor: Actor, template_id: int) -> list[TemplateAggregate]:
    response = client.delete(f"/templates/{template_id}", headers=actor.headers())
    assert response.status_code == 200, response.text
    return [TemplateAggregate.model_validate(item) for item in response.json()]


def _get_day(client: TestClient, actor: Actor, iso_date: str) -> DayAggregate:
    response = client.get(f"/days/{iso_date}", headers=actor.headers())
    assert response.status_code == 200, response.text
    return DayAggregate.model_validate(response.json())


def _count(db: Session, model: type[TemplateDay] | type[TemplateItem] | type[PlanDay]) -> int:
    db.expire_all()
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


THREE_DAYS: dict[str, object] = {
    "name": "  三分化  ",
    "length_days": "3",
    "days": [
        {
            "kind": "train",
            "title": "  推  ",
            "items": [{"exercise": "卧推"}, {"exercise": "   "}, {"exercise": " 肩推 "}],
        },
        {"kind": "rest", "title": "", "items": []},
        {"kind": "train", "title": None, "items": [{"exercise": "深蹲"}]},
    ],
}


# ---------- 创建 ----------


def test_create_keeps_skeleton(client: TestClient, actor_a: Actor) -> None:
    """FR-9.2：名称 strip、标题 strip 后空即 NULL、空动作名忽略、position 从 0 递增。"""
    body = _create(client, actor_a, THREE_DAYS)

    assert body.id > 0
    assert body.name == "三分化"
    assert body.length_days == 3
    assert [day.day_index for day in body.days] == [0, 1, 2]

    first = body.days[0]
    assert (first.kind, first.title) == ("train", "推")
    assert [(item.exercise, item.position) for item in first.items] == [("卧推", 0), ("肩推", 1)]

    second = body.days[1]
    assert (second.kind, second.title) == ("rest", None)
    assert second.items == []

    third = body.days[2]
    assert (third.kind, third.title) == ("train", None)
    assert [(item.exercise, item.position) for item in third.items] == [("深蹲", 0)]


def test_create_falls_back_to_default_name(client: TestClient, actor_a: Actor) -> None:
    """名称 strip 后为空（含纯空白与缺省）→「未命名循环」，不报错。"""
    payloads: list[dict[str, object]] = [
        {"length_days": "1"},
        {"name": "   ", "length_days": "1"},
        {"name": None},
    ]
    for payload in payloads:
        assert _create(client, actor_a, payload).name == "未命名循环"


def test_create_length_falls_back_to_eight(client: TestClient, actor_a: Actor) -> None:
    """FR-9.2：天数非法或缺省回退 8（`parse_sets` 只认 >0 整数，故 0/负数/小数也回退）。"""
    for length in ("abc", "0", "-3", "8.5", "天数", ""):
        body = _create(client, actor_a, {"length_days": length})
        assert body.length_days == 8, length
        # 缺的骨架由服务端补齐：默认训练日、无标题、无条目
        assert [day.day_index for day in body.days] == list(range(8))
        assert {day.kind for day in body.days} == {"train"}
        assert all(day.title is None and day.items == [] for day in body.days)

    missing = _create(client, actor_a, {})
    assert (missing.length_days, len(missing.days)) == (8, 8)


def test_create_truncates_length_to_twelve(client: TestClient, actor_a: Actor) -> None:
    """FR-9.2：超界静默截断 12（不报错），骨架也正好 12 行。"""
    body = _create(client, actor_a, {"length_days": "20"})
    assert (body.length_days, len(body.days)) == (12, 12)


def test_create_ignores_days_beyond_length(client: TestClient, actor_a: Actor) -> None:
    """v1 只读 `range(length)` 内的字段：`days` 多出来的天被忽略。"""
    body = _create(
        client,
        actor_a,
        {
            "length_days": "2",
            "days": [
                {"items": [{"exercise": "深蹲"}]},
                {"kind": "rest"},
                {"items": [{"exercise": "卧推"}]},
            ],
        },
    )
    assert [day.day_index for day in body.days] == [0, 1]
    assert body.days[1].kind == "rest"
    assert body.days[1].items == []
    assert all(item.exercise != "卧推" for day in body.days for item in day.items)


def test_create_normalizes_kind(client: TestClient, actor_a: Actor) -> None:
    """FR-9.2：只有精确的 `rest` 是休息日，其余（含大小写错、脏值、缺省）一律 train。"""
    body = _create(
        client,
        actor_a,
        {"length_days": "4", "days": [{"kind": "rest"}, {"kind": "REST"}, {"kind": "legs"}, {}]},
    )
    assert [day.kind for day in body.days] == ["rest", "train", "train", "train"]


def test_create_registers_exercises_in_own_library(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """模板条目建进本人动作库（FR-3.4 命名空间），不进别人的。"""
    own = _create(client, actor_a, THREE_DAYS)
    db_session.expire_all()
    rows = select(Exercise.name).where(Exercise.user_id == actor_a.user_id)
    names = set(db_session.scalars(rows))
    assert names == {"卧推", "肩推", "深蹲"}
    assert [item.exercise for day in own.days for item in day.items] == ["卧推", "肩推", "深蹲"]


def test_create_requires_token(client: TestClient) -> None:
    response = client.post("/templates", json={"length_days": "1"})
    assert response.status_code == 401


# ---------- 列表与隔离 ----------


def test_list_empty_for_new_user(client: TestClient, actor_a: Actor) -> None:
    assert _list(client, actor_a) == []


def test_list_orders_templates_days_and_items(client: TestClient, actor_a: Actor) -> None:
    """模板按 id 升序、天按 day_index、条目按 position（与创建顺序无关的显式排序）。"""
    first = _create(client, actor_a, THREE_DAYS)
    second = _create(client, actor_a, {"name": "两分化", "length_days": "2"})

    body = _list(client, actor_a)
    assert [template.id for template in body] == [first.id, second.id]
    assert [day.day_index for day in body[0].days] == [0, 1, 2]
    assert [item.position for item in body[0].days[0].items] == [0, 1]


def test_list_hides_other_users_templates(
    client: TestClient, actor_a: Actor, actor_b: Actor
) -> None:
    """FR-9.5：列表互不可见（连同天与条目）。"""
    _create(client, actor_a, {"name": "A 的循环", "length_days": "1"})
    _create(client, actor_b, {"name": "B 的循环", "length_days": "1", "days": [{"kind": "rest"}]})

    assert [template.name for template in _list(client, actor_a)] == ["A 的循环"]
    assert [template.name for template in _list(client, actor_b)] == ["B 的循环"]
    assert _list(client, actor_b)[0].days[0].kind == "rest"


# ---------- 删除 ----------


def test_delete_cascades_days_and_items(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """FR-9.4：删模板级联天与条目（ORM cascade + FK ON DELETE CASCADE），返回剩余列表。"""
    doomed = _create(client, actor_a, THREE_DAYS)
    survivor = _create(client, actor_a, {"name": "留着的", "length_days": "1"})
    assert (_count(db_session, TemplateDay), _count(db_session, TemplateItem)) == (4, 3)

    remaining = _delete(client, actor_a, doomed.id)
    assert [template.id for template in remaining] == [survivor.id]
    assert (_count(db_session, TemplateDay), _count(db_session, TemplateItem)) == (1, 0)


def test_delete_missing_template_is_404(client: TestClient, actor_a: Actor) -> None:
    response = client.delete("/templates/999", headers=actor_a.headers())
    assert response.status_code == 404
    assert response.json()["detail"] == NOT_FOUND_DETAIL


def test_delete_other_users_template_is_404(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories, db_session: Session
) -> None:
    """FR-9.5：跨用户删除同码同文案，且原模板一行都不少。"""
    template = make.template(actor_a, name="A 的循环", kinds=("train",))
    response = client.delete(f"/templates/{template.id}", headers=actor_b.headers())
    assert response.status_code == 404
    assert response.json()["detail"] == NOT_FOUND_DETAIL

    assert _count(db_session, TemplateDay) == 1
    assert [body.name for body in _list(client, actor_a)] == ["A 的循环"]


# ---------- apply ----------


def test_apply_creates_plan_days_from_start(client: TestClient, actor_a: Actor) -> None:
    """FR-9.3：从 start 按 day_index 逐日铺排，kind/title/动作骨架都抄过去，模板不含重量。"""
    template = _create(client, actor_a, THREE_DAYS)

    result = _apply(client, actor_a, template.id, START_ISO)
    assert (result.created, result.skipped) == (3, 0)
    assert result.skipped_dates == []

    first = _get_day(client, actor_a, "2026-03-01")
    assert (first.kind, first.title) == ("train", "推")
    assert [item.exercise for item in first.planned_items] == ["卧推", "肩推"]
    assert [item.position for item in first.planned_items] == [0, 1]
    assert all(
        (item.weight_kg, item.sets, item.reps) == (None, None, None) for item in first.planned_items
    )
    assert first.actual_items == [] and first.note == ""

    rest = _get_day(client, actor_a, "2026-03-02")
    assert (rest.kind, rest.title) == ("rest", None)
    assert rest.planned_items == []

    third = _get_day(client, actor_a, "2026-03-03")
    assert [item.exercise for item in third.planned_items] == ["深蹲"]


def test_apply_skips_existing_plan_day_without_overwriting(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """FR-9.3：已有 PlanDay 的日期跳过且绝不覆盖 —— 原 title 与原计划条目原封不动。"""
    template = _create(client, actor_a, THREE_DAYS)
    blocked = date(2026, 3, 2)
    existing = make.plan_day(actor_a, blocked, kind="rest", title="原有计划")
    kept = make.planned_item(actor_a, existing, exercise="原有动作", weight_kg=80.0, sets=5)

    result = _apply(client, actor_a, template.id, START_ISO)
    assert (result.created, result.skipped) == (2, 1)
    assert result.skipped_dates == [blocked]

    body = _get_day(client, actor_a, blocked.isoformat())
    assert (body.kind, body.title) == ("rest", "原有计划")
    assert [(item.id, item.exercise) for item in body.planned_items] == [(kept.id, "原有动作")]
    assert (body.planned_items[0].weight_kg, body.planned_items[0].sets) == (80.0, 5)


def test_apply_twice_skips_everything(client: TestClient, actor_a: Actor) -> None:
    """第二次 apply 全跳过：`created` 归零，`skipped_dates` 给全部日期。"""
    template = _create(client, actor_a, THREE_DAYS)
    assert _apply(client, actor_a, template.id, START_ISO).created == 3

    again = _apply(client, actor_a, template.id, START_ISO)
    assert (again.created, again.skipped) == (0, 3)
    assert again.skipped_dates == [START + timedelta(days=offset) for offset in range(3)]


def test_apply_ignores_other_users_plan_day(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories
) -> None:
    """跳过判定查的是当前用户的 (user_id, date)：B 当天有计划不阻挡 A，B 的行也不被动。"""
    template = _create(client, actor_a, THREE_DAYS)
    blocked_for_b = date(2026, 3, 2)
    b_day = make.plan_day(actor_b, blocked_for_b, title="B 的计划")
    make.planned_item(actor_b, b_day, exercise="B 的动作")

    result = _apply(client, actor_a, template.id, START_ISO)
    assert (result.created, result.skipped) == (3, 0)
    assert result.skipped_dates == []

    theirs = _get_day(client, actor_b, blocked_for_b.isoformat())
    assert theirs.title == "B 的计划"
    assert [item.exercise for item in theirs.planned_items] == ["B 的动作"]


def test_apply_other_users_template_is_404(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories
) -> None:
    """HLD §12.0 templates 行明写：跨用户 apply 404，且不给 B 铺出任何计划日。"""
    template = make.template(actor_a, name="A 的循环", kinds=("train", "rest"))
    response = client.post(
        f"/templates/{template.id}/apply", json={"start": START_ISO}, headers=actor_b.headers()
    )
    assert response.status_code == 404
    assert response.json()["detail"] == NOT_FOUND_DETAIL
    assert _get_day(client, actor_b, START_ISO).kind is None
    assert _get_day(client, actor_a, START_ISO).kind is None


def test_apply_missing_template_is_404(client: TestClient, actor_a: Actor) -> None:
    response = client.post(
        "/templates/999/apply", json={"start": START_ISO}, headers=actor_a.headers()
    )
    assert response.status_code == 404
    assert response.json()["detail"] == NOT_FOUND_DETAIL


def test_apply_invalid_start_is_400(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """HLD §9.2：日期格式非法是 400（不是 Pydantic 的 422），且一天都不铺。"""
    template = _create(client, actor_a, THREE_DAYS)
    for start in ("2026-13-01", "2026-02-30", "03/01/2026", ""):
        response = client.post(
            f"/templates/{template.id}/apply", json={"start": start}, headers=actor_a.headers()
        )
        assert response.status_code == 400, start
        assert response.json()["detail"] == INVALID_DATE_DETAIL
    assert _count(db_session, PlanDay) == 0


# ---------- 脏行 ----------


def test_item_pointing_at_other_users_exercise_is_invisible(
    client: TestClient,
    actor_a: Actor,
    actor_b: Actor,
    make: Factories,
    db_session: Session,
) -> None:
    """条目指向别人动作库时：列表里看不到，apply 也不抄（即使行挂在 A 的模板下）。"""
    template = make.template(actor_a, name="A 的循环", kinds=("train",), length_days=1)
    day = template.days[0]
    foreign = make.exercise(actor_b, "B 的动作")
    db_session.add(
        TemplateItem(
            user_id=actor_a.user_id,
            template_day_id=day.id,
            exercise_id=foreign.id,
            position=0,
        )
    )
    db_session.commit()

    assert _list(client, actor_a)[0].days[0].items == []

    assert _apply(client, actor_a, template.id, START_ISO).created == 1
    assert _get_day(client, actor_a, START_ISO).planned_items == []
