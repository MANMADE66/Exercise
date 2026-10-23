"""路径常量与环境变量（骨架版：只保留 health 端点需要的最小集合）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


@dataclass(frozen=True)
class Settings:
    version: str = "0.1.0"
    # dev 下前端跑在 5173；prod 由本进程托管静态文件，不需要 CORS
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    dev_cors: bool = field(default_factory=lambda: os.getenv("TL_ENV", "dev") != "prod")


settings = Settings()
