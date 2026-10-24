"""测试固件：每个用例一套临时库（不碰 backend/data）。

除基础夹具外，这里交付**归属隔离测试助手**（票 08）：
- `actor_a` / `actor_b`：两个用户 + 各自有效的 Bearer token（不跑 bcrypt，隔离测试不需要登录）；
- `make`：工厂，造计划日 / 计划条目 / 实际条目 / 模板（含天与条目）/ 周体重 / 动作库。
业务域票直接复用，不必再手写 A/B 数据。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import TypeVar

import pytest
from app.core.config import Settings, settings
from app.core.security import TokenPolicy, create_access_token
from app.main import create_app
from app.models import (
    ActualItem,
    BodyMetric,
    CycleTemplate,
    Exercise,
    PlanDay,
    PlannedItem,
    TemplateDay,
    TemplateItem,
    User,
)
from app.services import isolation
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, sessionmaker

RowT = TypeVar("RowT")

UNUSABLE_PASSWORD_HASH = "!isolation-tests-do-not-login"


@dataclass(frozen=True)
class Actor:
    """一个用户及其 token（隔离测试里的「当前用户」A / B）。"""

    user_id: int
    username: str
    token: str

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


class Factories:
    """造数据并 `commit()`：HTTP 请求用另一个 session，不提交就看不见。

    只造数据、不替业务规则：长度截断、apply 跳过、prefill 幂等都由 service 负责。
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ---------- 动作库 ----------

    def exercise(
        self, actor: Actor, name: str = "深蹲", *, body_part: str | None = None
    ) -> Exercise:
        """按 (user_id, name) 取或建——命名空间隔离的既有语义（SRS FR-3.4）。"""
        existing = isolation.find_exercise(self._db, user_id=actor.user_id, name=name)
        if existing is not None:
            return existing
        return self._add(Exercise(user_id=actor.user_id, name=name, body_part=body_part))

    # ---------- 日历 ----------

    def plan_day(
        self,
        actor: Actor,
        on: date,
        *,
        kind: str = "train",
        title: str | None = None,
        note: str | None = None,
    ) -> PlanDay:
        return self._add(PlanDay(user_id=actor.user_id, date=on, kind=kind, title=title, note=note))

    def planned_item(
        self,
        actor: Actor,
        day: PlanDay,
        *,
        exercise: str = "深蹲",
        weight_kg: float | None = None,
        sets: int | None = None,
        reps: str | None = None,
        position: int | None = None,
    ) -> PlannedItem:
        return self._add(
            PlannedItem(
                user_id=actor.user_id,
                plan_day_id=day.id,
                exercise_id=self.exercise(actor, exercise).id,
                weight_kg=weight_kg,
                sets=sets,
                reps=reps,
                position=self._auto_position(
                    position,
                    select(func.count(PlannedItem.id)).where(PlannedItem.plan_day_id == day.id),
                ),
            )
        )

    def actual_item(
        self,
        actor: Actor,
        day: PlanDay,
        *,
        exercise: str = "深蹲",
        planned_item: PlannedItem | None = None,
        weight_kg: float | None = None,
        sets: int | None = None,
        reps: str | None = None,
        note: str | None = None,
        position: int | None = None,
    ) -> ActualItem:
        return self._add(
            ActualItem(
                user_id=actor.user_id,
                plan_day_id=day.id,
                planned_item_id=None if planned_item is None else planned_item.id,
                exercise_id=self.exercise(actor, exercise).id,
                weight_kg=weight_kg,
                sets=sets,
                reps=reps,
                note=note,
                position=self._auto_position(
                    position,
                    select(func.count(ActualItem.id)).where(ActualItem.plan_day_id == day.id),
                ),
            )
        )

    # ---------- 模板 ----------

    def template(
        self,
        actor: Actor,
        *,
        name: str = "三分化",
        kinds: Sequence[str] = ("train", "train", "train"),
        length_days: int | None = None,
    ) -> CycleTemplate:
        """建模板骨架：`kinds` 一天一项，`day_index` 从 0 起（与 v1 一致）。"""
        template = self._add(
            CycleTemplate(
                user_id=actor.user_id,
                name=name,
                length_days=len(kinds) if length_days is None else length_days,
            )
        )
        for index, kind in enumerate(kinds):
            self.template_day(actor, template, day_index=index, kind=kind)
        return template

    def template_day(
        self,
        actor: Actor,
        template: CycleTemplate,
        *,
        day_index: int | None = None,
        kind: str = "train",
        title: str | None = None,
    ) -> TemplateDay:
        return self._add(
            TemplateDay(
                user_id=actor.user_id,
                template_id=template.id,
                day_index=self._auto_position(
                    day_index,
                    select(func.count(TemplateDay.id)).where(
                        TemplateDay.template_id == template.id
                    ),
                ),
                kind=kind,
                title=title,
            )
        )

    def template_item(
        self,
        actor: Actor,
        day: TemplateDay,
        *,
        exercise: str = "深蹲",
        sets: int | None = None,
        reps: str | None = None,
        position: int | None = None,
    ) -> TemplateItem:
        """模板条目不含重量（SRS FR-9.2）。"""
        return self._add(
            TemplateItem(
                user_id=actor.user_id,
                template_day_id=day.id,
                exercise_id=self.exercise(actor, exercise).id,
                sets=sets,
                reps=reps,
                position=self._auto_position(
                    position,
                    select(func.count(TemplateItem.id)).where(
                        TemplateItem.template_day_id == day.id
                    ),
                ),
            )
        )

    # ---------- 周体重 ----------

    def body_metric(
        self,
        actor: Actor,
        week_start: date,
        weight_kg: float,
        *,
        body_fat_pct: float | None = None,
        note: str | None = None,
    ) -> BodyMetric:
        return self._add(
            BodyMetric(
                user_id=actor.user_id,
                week_start=week_start,
                weight_kg=weight_kg,
                body_fat_pct=body_fat_pct,
                note=note,
            )
        )

    # ---------- 内部 ----------

    def _add(self, row: RowT) -> RowT:
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def _auto_position(self, explicit: int | None, count_stmt: Select[int]) -> int:
        """缺省顺序 = 同一天现有条目数（模拟 days_service 的 position 维护）。"""
        if explicit is not None:
            return explicit
        return int(self._db.scalar(count_stmt) or 0)


@pytest.fixture()
def app_settings(tmp_path: Path) -> Settings:
    return replace(
        settings,
        data_dir=tmp_path / "data",
        db_path_override=tmp_path / "data" / "test.db",
        secret_env=None,
    )


@pytest.fixture()
def app(app_settings: Settings) -> FastAPI:
    return create_app(app_settings)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(app: FastAPI, client: TestClient) -> Iterator[Session]:
    """直连同一个临时库的会话（lifespan 已由 client 启动）。"""
    factory: sessionmaker[Session] = app.state.session_factory
    with factory() as session:
        yield session


@pytest.fixture()
def actor_factory(app: FastAPI, db_session: Session) -> Callable[[str], Actor]:
    """建用户 + 签 token；不走 /auth/register（bcrypt 慢，且隔离测试不验证登录）。"""

    def _create(username: str) -> Actor:
        user = User(username=username, password_hash=UNUSABLE_PASSWORD_HASH)
        db_session.add(user)
        db_session.commit()
        policy = TokenPolicy(
            secret=app.state.secret_key,
            ttl_days=app.state.settings.token_ttl_days,
            algorithm=app.state.settings.jwt_algorithm,
        )
        token = create_access_token(user.id, policy)
        return Actor(user_id=user.id, username=username, token=token)

    return _create


@pytest.fixture()
def actor_a(actor_factory: Callable[[str], Actor]) -> Actor:
    return actor_factory("alice")


@pytest.fixture()
def actor_b(actor_factory: Callable[[str], Actor]) -> Actor:
    return actor_factory("bob")


@pytest.fixture()
def make(db_session: Session) -> Factories:
    return Factories(db_session)
