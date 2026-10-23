"""路径常量与环境变量（HLD §5.1 core/config.py、§4.2 第 5 条）。

环境变量一律 `TL_` 前缀；运行数据（app.db / secret.key）默认落在 `backend/data/`。
测试通过 `dataclasses.replace(settings, data_dir=...)` 换库，不依赖环境变量。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"

DEFAULT_DB_FILENAME = "app.db"
DEFAULT_SECRET_FILENAME = "secret.key"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    version: str = "0.1.0"
    # dev 下前端跑在 5173；prod 由本进程托管静态文件，不需要 CORS
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    dev_cors: bool = field(default_factory=lambda: os.getenv("TL_ENV", "dev") != "prod")
    # 运行数据目录：TL_DATA_DIR 覆盖
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("TL_DATA_DIR") or DATA_DIR).expanduser()
    )
    # 整路径覆盖（优先于 data_dir/app.db）；测试与一次性脚本用
    db_path_override: Path | None = field(
        default_factory=lambda: (
            Path(os.environ["TL_DB_PATH"]).expanduser() if os.getenv("TL_DB_PATH") else None
        )
    )
    # JWT 密钥：TL_SECRET 覆盖（优先于 secret.key 文件，HLD §7）
    secret_env: str | None = field(default_factory=lambda: os.getenv("TL_SECRET") or None)
    token_ttl_days: int = field(default_factory=lambda: _env_int("TL_TOKEN_TTL_DAYS", 7))
    jwt_algorithm: str = "HS256"

    @property
    def db_path(self) -> Path:
        if self.db_path_override is not None:
            return self.db_path_override
        return self.data_dir / DEFAULT_DB_FILENAME

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / DEFAULT_SECRET_FILENAME


settings = Settings()
