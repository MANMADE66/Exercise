"""周体重 upsert（HLD §12.0「metrics」行；SRS FR-10）。

覆盖点：
- 同周 upsert：第二次 PUT 改 weight **只更新那一行**（行数不变、id 不变）；
- 周一起点归一：传周三 / 周日都落到该周周一那一行（路径参数不假设是周一）；
- 非法体重 → **422 且表内零变化**（FR-10.2：不落库）；
- 可选字段容错：body_fat 认不出 → NULL 不报错，note 纯空白 → NULL；PUT 是整体替换；
- 隔离：A 与 B 同一周各一行，B 的 PUT 不改 A 的行；
- 日期格式非法 → 400（HLD §9.2）；无 token → 401。

响应按生成契约 `BodyMetricOut` 解析（与 `test_days.py` / `test_calendar.py` 同一手法：断言用的是
`api-types.ts` 里的同一批字段名，契约形状一变就在这里炸）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from app.models import BodyMetric
from app.routers.days import INVALID_DATE_DETAIL
from app.schemas import WEIGHT_INVALID_MESSAGE, BodyMetricOut
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import Actor, Factories

MON = date(2026, 1, 5)  # 2026-01-05 是周一
WED = "2026-01-07"  # 同一周的周三
SUN = "2026-01-11"  # 同一周的周日


def _put(
    client: TestClient, actor: Actor, week_start: str, **payload: object
) -> tuple[int, dict[str, Any]]:
    response = client.put(f"/metrics/{week_start}", json=payload, headers=actor.headers())
    body: dict[str, Any] = response.json()
    return response.status_code, body


def _put_ok(client: TestClient, actor: Actor, week_start: str, **payload: object) -> BodyMetricOut:
    status_code, body = _put(client, actor, week_start, **payload)
    assert status_code == 200, body
    return BodyMetricOut.model_validate(body)


def _rows(db: Session, actor: Actor) -> list[BodyMetric]:
    """直读表内属于该用户的行（HTTP 写走另一个 session，先 expire 再看新值）。"""
    db.expire_all()
    return list(
        db.scalars(
            select(BodyMetric)
            .where(BodyMetric.user_id == actor.user_id)
            .order_by(BodyMetric.week_start)
        )
    )


def _detail_of(payload: dict[str, Any]) -> str:
    """取错误体 detail：字符串（400/404）或 422 数组首条 msg（Pydantic 原生）。"""
    detail = payload["detail"]
    if isinstance(detail, str):
        return detail
    assert isinstance(detail, list) and detail
    msg = detail[0]["msg"]
    assert isinstance(msg, str)
    return msg


def test_first_put_creates_the_week_row(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """首次 PUT 落一行：路径上的周三归一到周一，文本体重按 v1 的容错解析。"""
    body = _put_ok(client, actor_a, WED, weight="80kg", body_fat="18,5", note="  减脂 ")

    assert (body.week_start, body.weight_kg) == (MON, 80.0)
    assert (body.body_fat_pct, body.note) == (18.5, "减脂")
    rows = _rows(db_session, actor_a)
    assert len(rows) == 1
    assert rows[0].week_start == MON


def test_second_put_same_week_updates_the_same_row(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """同周再 PUT 是 upsert：行数与 id 不变，值是最后一次（没传的可选字段被替换成 NULL）。"""
    _put_ok(client, actor_a, WED, weight="80", body_fat="18.5", note="减脂")
    row_id = _rows(db_session, actor_a)[0].id

    body = _put_ok(client, actor_a, SUN, weight="79")

    assert (body.week_start, body.weight_kg) == (MON, 79.0)
    assert (body.body_fat_pct, body.note) == (None, None)
    rows = _rows(db_session, actor_a)
    assert len(rows) == 1
    assert (rows[0].id, rows[0].weight_kg) == (row_id, 79.0)


@pytest.mark.parametrize("iso_date", ["2026-01-05", WED, SUN])
def test_any_day_of_the_week_lands_on_that_monday(
    client: TestClient, actor_a: Actor, db_session: Session, iso_date: str
) -> None:
    """路径参数叫 week_start，但周三 / 周日同样落到该周周一那一行（v1 无「必须周一」约束）。"""
    body = _put_ok(client, actor_a, iso_date, weight="80")

    assert body.week_start == MON
    assert body.week_start.weekday() == 0
    assert [row.week_start for row in _rows(db_session, actor_a)] == [MON]


@pytest.mark.parametrize("weight", ["", "   ", "abc", "0", "-3", "kg"])
def test_invalid_weight_is_422_and_writes_nothing(
    client: TestClient, actor_a: Actor, db_session: Session, weight: str
) -> None:
    """FR-10.2：体重非法 → 422 + 可展示的中文消息，且**一行都不写**。"""
    status_code, body = _put(client, actor_a, WED, weight=weight)

    assert status_code == 422
    assert _detail_of(body) == WEIGHT_INVALID_MESSAGE
    assert _rows(db_session, actor_a) == []


def test_invalid_weight_leaves_an_existing_row_untouched(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """已有的那一行也不能被非法 PUT 改动（不是「先落库再报错」）。"""
    _put_ok(client, actor_a, WED, weight="80", note="减脂")

    status_code, _ = _put(client, actor_a, WED, weight="轻了")

    assert status_code == 422
    rows = _rows(db_session, actor_a)
    assert len(rows) == 1
    assert (rows[0].weight_kg, rows[0].note) == (80.0, "减脂")


def test_body_fat_and_note_are_lenient(client: TestClient, actor_a: Actor) -> None:
    """可选字段不报错：体脂认不出 → NULL，备注纯空白 → NULL（v1 同语义）。"""
    body = _put_ok(client, actor_a, WED, weight="80", body_fat="abc", note="   ")

    assert (body.body_fat_pct, body.note) == (None, None)


def test_users_keep_their_own_row_for_the_same_week(
    client: TestClient, actor_a: Actor, actor_b: Actor, db_session: Session
) -> None:
    """唯一键是 (user_id, week_start)：B 写同一周有自己的行，绝不动 A 那一行。"""
    _put_ok(client, actor_a, WED, weight="80", note="A 的")

    body_b = _put_ok(client, actor_b, WED, weight="70", note="B 的")

    assert body_b.weight_kg == 70.0
    rows_a = _rows(db_session, actor_a)
    rows_b = _rows(db_session, actor_b)
    assert [(row.weight_kg, row.note) for row in rows_a] == [(80.0, "A 的")]
    assert [(row.weight_kg, row.note) for row in rows_b] == [(70.0, "B 的")]

    # A 再写一次也不会碰 B 的行
    _put_ok(client, actor_a, WED, weight="81")
    assert [row.weight_kg for row in _rows(db_session, actor_b)] == [70.0]


def test_invalid_path_date_is_400_not_422(
    client: TestClient, actor_a: Actor, db_session: Session
) -> None:
    """日期格式非法走 400（HLD §9.2），与体重非法的 422 是两条语义。"""
    for iso_date in ("not-a-date", "2026-02-30", "2026-1-5"):
        status_code, body = _put(client, actor_a, iso_date, weight="80")
        assert status_code == 400
        assert _detail_of(body) == INVALID_DATE_DETAIL
    assert _rows(db_session, actor_a) == []


def test_metrics_requires_auth(client: TestClient, db_session: Session) -> None:
    response = client.put(f"/metrics/{WED}", json={"weight": "80"})

    assert response.status_code == 401
    assert list(db_session.scalars(select(BodyMetric))) == []


def test_written_metric_shows_up_in_the_calendar_week_row(
    client: TestClient, actor_a: Actor
) -> None:
    """写路径与读路径共用同一行：PUT 之后月历该周就有 metric（读仍在 calendar_service）。"""
    _put_ok(client, actor_a, WED, weight="80")

    calendar = client.get("/calendar", params={"month": "2026-01"}, headers=actor_a.headers())

    assert calendar.status_code == 200, calendar.text
    weeks = calendar.json()["weeks"]
    assert weeks  # 2026-01 至少一周
    first = next(week for week in weeks if week["week_start"] == "2026-01-05")
    assert first["metric"] is not None
    assert first["metric"]["weight_kg"] == 80.0


def test_make_factory_row_is_updatable(
    client: TestClient, actor_a: Actor, make: Factories, db_session: Session
) -> None:
    """夹具直接造的既有行同样能被 PUT 覆盖（不是「只认自己插入的行」）。"""
    make.body_metric(actor_a, MON, 88.0, note="旧值")

    body = _put_ok(client, actor_a, WED, weight="86")

    assert body.weight_kg == 86.0
    assert [(row.weight_kg, row.note) for row in _rows(db_session, actor_a)] == [(86.0, None)]
