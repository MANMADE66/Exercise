"""月历聚合（HLD §12.0「calendar」行；SRS FR-4）。

覆盖点：
- 非法 / 缺省 month 静默回退当月（服务端不报错，FR-4.2）；
- 网格整周补齐 null（周一为起点，首行 / 末行）；
- 每格带 PlanDay 的 kind / title（无 PlanDay → null，与补齐位的 null 格区分）；
- logged_dates = 有实际条目的日期集合，不是「有计划日」的日期；
- 周行 = 周一起点（跨月行挂上一周的周一）+ 该周 BodyMetric 挂对行；
- 隔离：B 的计划日 / 记录日 / 周体重不出现在 A 的日历（logged_dates 的 join 也带 user_id）；
- 无 token → 401。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import Actor, Factories

# 2026-02：2/1 是周日 → 首行补 6 个 null；28 天 → 5 周，末行补 1 个 null
FEB = "2026-02"
# 2026-07：7/1 是周三 → 首行补 2 个 null；首行 week_start = 2026-06-29（落在上一月）
JUL = "2026-07"


def _get(client: TestClient, actor: Actor, month: str | None = None) -> dict[str, Any]:
    params = {} if month is None else {"month": month}
    response = client.get("/calendar", params=params, headers=actor.headers())
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _cells(body: dict[str, Any]) -> list[dict[str, Any] | None]:
    return [cell for week in body["weeks"] for cell in week["cells"]]


def test_invalid_month_falls_back_to_current(client: TestClient, actor_a: Actor) -> None:
    """非法月份不报错：回退当月，响应里的 year/month 是生效值（FR-4.2）。"""
    today = date.today()
    for raw in ("2026-13", "not-a-month", "2026/02", ""):
        body = _get(client, actor_a, raw)
        assert body["year"] == today.year
        assert body["month"] == today.month


def test_missing_month_falls_back_to_current(client: TestClient, actor_a: Actor) -> None:
    today = date.today()
    body = _get(client, actor_a)
    assert (body["year"], body["month"]) == (today.year, today.month)


def test_grid_is_padded_to_full_weeks(client: TestClient, actor_a: Actor) -> None:
    """首行 / 末行补 null；每周恒 7 格；当月的每一天都在格子里（FR-4.1）。"""
    body = _get(client, actor_a, FEB)

    assert len(body["weeks"]) == 5
    assert all(len(week["cells"]) == 7 for week in body["weeks"])

    cells = _cells(body)
    assert cells[:6] == [None] * 6  # 2/1 周日：周一到周六补 6 格
    assert cells[-1] is None  # 2/28 周六：周日补 1 格

    dates = [cell["date"] for cell in cells if cell is not None]
    assert dates == [f"2026-02-{d:02d}" for d in range(1, 29)]


def test_cells_carry_plan_day_kind_and_title(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """有 PlanDay 的格子带 kind/title；没有的是空壳（kind/title 为 null），但格子本身在。"""
    make.plan_day(actor_a, date(2026, 2, 10), kind="train", title="腿")
    make.plan_day(actor_a, date(2026, 2, 11), kind="rest")  # 无标题休息日

    body = _get(client, actor_a, FEB)
    by_date = {cell["date"]: cell for cell in _cells(body) if cell is not None}

    assert by_date["2026-02-10"] == {"date": "2026-02-10", "kind": "train", "title": "腿"}
    assert by_date["2026-02-11"] == {"date": "2026-02-11", "kind": "rest", "title": None}
    assert by_date["2026-02-12"] == {"date": "2026-02-12", "kind": None, "title": None}


def test_logged_dates_require_actual_items(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """判据是「存在实际条目」：只有计划日不算；月外的记录不进集合。"""
    planned_only = make.plan_day(actor_a, date(2026, 2, 3), title="只排了计划")
    logged = make.plan_day(actor_a, date(2026, 2, 4))
    make.actual_item(actor_a, logged)
    make.actual_item(actor_a, logged, exercise="硬拉")  # 多条仍只出现一次
    out_of_month = make.plan_day(actor_a, date(2026, 3, 2))
    make.actual_item(actor_a, out_of_month)

    body = _get(client, actor_a, FEB)
    by_date = {cell["date"]: cell for cell in _cells(body) if cell is not None}

    # 只排了计划的日期在格子里有标签，但不算已记录
    assert by_date[planned_only.date.isoformat()]["title"] == "只排了计划"
    assert body["logged_dates"] == ["2026-02-04"]


def test_week_rows_start_on_monday_and_carry_metric(
    client: TestClient, actor_a: Actor, make: Factories
) -> None:
    """week_start 恒为周一；跨月首行挂上一周的周一；该周体重挂对行。"""
    make.body_metric(actor_a, date(2026, 6, 29), 80.0, body_fat_pct=18.5, note="减脂")
    make.body_metric(actor_a, date(2026, 7, 13), 79.0)
    make.body_metric(actor_a, date(2026, 7, 6), 81.0)  # 有记录但不该挂错行

    body = _get(client, actor_a, JUL)
    weeks = body["weeks"]

    assert [w["week_start"] for w in weeks] == [
        "2026-06-29",
        "2026-07-06",
        "2026-07-13",
        "2026-07-20",
        "2026-07-27",
    ]
    assert all(date.fromisoformat(w["week_start"]).weekday() == 0 for w in weeks)

    first, _, third, *_ = weeks
    assert first["metric"] == {
        "week_start": "2026-06-29",
        "weight_kg": 80.0,
        "body_fat_pct": 18.5,
        "note": "减脂",
    }
    assert third["metric"]["weight_kg"] == 79.0
    assert weeks[1]["metric"]["weight_kg"] == 81.0
    assert weeks[3]["metric"] is None  # 没填的周就是 null，不存在「空记录」


def test_calendar_is_isolated_between_users(
    client: TestClient, actor_a: Actor, actor_b: Actor, make: Factories
) -> None:
    """B 的计划日 / 记录日 / 周体重都不出现在 A 的日历（join 查询同样收窄）。"""
    b_day = make.plan_day(actor_b, date(2026, 2, 5), title="B 的训练")
    make.actual_item(actor_b, b_day)
    make.body_metric(actor_b, date(2026, 2, 2), 70.0)

    body = _get(client, actor_a, FEB)
    by_date = {cell["date"]: cell for cell in _cells(body) if cell is not None}

    assert by_date["2026-02-05"] == {"date": "2026-02-05", "kind": None, "title": None}
    assert body["logged_dates"] == []
    assert all(week["metric"] is None for week in body["weeks"])

    # 反向也成立：A 有自己的数据时 B 看不到
    a_day = make.plan_day(actor_a, date(2026, 2, 6), title="A 的训练")
    make.actual_item(actor_a, a_day)
    make.body_metric(actor_a, date(2026, 2, 2), 90.0)

    body_b = _get(client, actor_b, FEB)
    by_date_b = {cell["date"]: cell for cell in _cells(body_b) if cell is not None}
    assert by_date_b["2026-02-06"] == {"date": "2026-02-06", "kind": None, "title": None}
    assert body_b["logged_dates"] == ["2026-02-05"]
    # 2/2 是周一 → 它属于第二行（首行是 1/26 那周）
    assert body_b["weeks"][0]["metric"] is None
    assert body_b["weeks"][1]["metric"]["weight_kg"] == 70.0


def test_calendar_requires_auth(client: TestClient) -> None:
    assert client.get("/calendar").status_code == 401
