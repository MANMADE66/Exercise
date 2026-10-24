"""错误归一：404 的唯一产出点（HLD §8.3、§9.2；SRS FR-3.2）。

「资源不存在」与「资源不属于当前用户」必须**同码同文案**，否则状态码或文案的差异
本身就是资源枚举的旁路（CONTEXT.md「归属隔离」）。

分工：
- service 层只抛 `NotFoundError`（不带消息，不拼文案）；
- 文案与 HTTP 映射都在这里，由 `main.create_app` 注册成全局处理器 —— 业务 router
  不需要为 404 写 try/except，也就无处写歪。
"""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse

NOT_FOUND_DETAIL = "资源不存在"


class NotFoundError(Exception):
    """不存在 / 不属于当前用户 / 父子链归属不一致 —— 三者必须不可区分（→ 404）。"""


def not_found_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """`NotFoundError` 的唯一出口：404 + 统一错误体（`{"detail": ...}`）。"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": NOT_FOUND_DETAIL},
    )
