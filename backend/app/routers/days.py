"""日聚合端点（SRS FR-5、HLD §9.1、§9.2）。

薄层：解析路径参数 → `CurrentUser` → service 聚合返回。两条错误语义刻意不共用 helper：

- days：日期格式非法 → **400**（HLD §9.2「日期或月份格式非法」）。路径参数必须收 `str`
  自行解析——标成 `datetime.date` 会让 FastAPI 直接吐 422，与契约不符；
- calendar 的 `?month=` 非法 → 静默回退当月（FR-4.2，票 10 注释）。这里不提供可复用的
  「日期参数化」helper，避免两套语义被一个函数糅在一起。

本文件随票 11/12/13 增补写端点，全部返回当天聚合（D7）。路径资源分两组：`/days/...` 以
日期定位（`router`），`/plan-items/...` 以条目 id 定位（`plan_items_router`，同样只做映射）。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser
from app.core.errors import NOT_FOUND_DETAIL
from app.db import get_db
from app.parsing import parse_day
from app.schemas import DayAggregate, PlanItemCreate, PlanItemMove
from app.services import days_service

router = APIRouter(prefix="/days", tags=["days"])
plan_items_router = APIRouter(prefix="/plan-items", tags=["days"])

DbSession = Annotated[Session, Depends(get_db)]

INVALID_DATE_DETAIL = "日期格式非法，需 YYYY-MM-DD"


def parse_day_or_400(iso_date: str) -> date:
    """路径参数 `{iso_date}` → `date`；解析留给 `app/parsing.py`（不抛错），400 在这里产出。"""
    parsed = parse_day(iso_date)
    if parsed is None:
        _invalid_date()
    return parsed


def _invalid_date() -> NoReturn:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_DATE_DETAIL)


@router.get(
    "/{iso_date}",
    response_model=DayAggregate,
    summary="日聚合",
    responses={400: {"description": INVALID_DATE_DETAIL}},
)
def read_day(iso_date: str, db: DbSession, current_user: CurrentUser) -> DayAggregate:
    """读取整天聚合；当天没有任何记录时返回空结构，**不落库**（FR-5.2）。"""
    return days_service.aggregate_day(db, user_id=current_user.id, day=parse_day_or_400(iso_date))


@router.post(
    "/{iso_date}/plan-items",
    response_model=DayAggregate,
    summary="添加计划条目",
    responses={400: {"description": INVALID_DATE_DETAIL}},
)
def create_plan_item(
    iso_date: str, payload: PlanItemCreate, db: DbSession, current_user: CurrentUser
) -> DayAggregate:
    """添加计划条目（FR-6.1）；动作名自动建入本人动作库，空动作名在契约层就已 422。"""
    return days_service.add_planned_item(
        db,
        user_id=current_user.id,
        day=parse_day_or_400(iso_date),
        exercise=payload.exercise,
        weight=payload.weight,
        sets=payload.sets,
        reps=payload.reps,
    )


@plan_items_router.delete(
    "/{plan_item_id}",
    response_model=DayAggregate,
    summary="删除计划条目",
    responses={404: {"description": NOT_FOUND_DETAIL}},
)
def delete_plan_item(plan_item_id: int, db: DbSession, current_user: CurrentUser) -> DayAggregate:
    """删除计划条目（FR-6.2）：关联的实际条目保留，其 `planned_item_id` 置空。"""
    return days_service.delete_planned_item(
        db, user_id=current_user.id, planned_item_id=plan_item_id
    )


@plan_items_router.post(
    "/{plan_item_id}/move",
    response_model=DayAggregate,
    summary="上下移动计划条目",
    responses={404: {"description": NOT_FOUND_DETAIL}},
)
def move_plan_item(
    plan_item_id: int, payload: PlanItemMove, db: DbSession, current_user: CurrentUser
) -> DayAggregate:
    """上下移动（FR-6.3）：边界（首个上移 / 末个下移）静默成功。"""
    return days_service.move_planned_item(
        db, user_id=current_user.id, planned_item_id=plan_item_id, direction=payload.direction
    )
