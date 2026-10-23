"""Pydantic 请求/响应模型。

骨架阶段只有存活探针；后续按 HLD §9 的聚合契约扩展。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="服务状态")
    version: str = Field(description="API 版本号")
