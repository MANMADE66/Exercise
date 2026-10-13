from pathlib import Path

from flask import Flask
from sqlalchemy.engine import URL

from app.db import db


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)

    if config:
        app.config.update(config)

    if "SQLALCHEMY_DATABASE_URI" not in app.config:
        data_dir = Path(app.root_path).parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        # 用 URL 对象而不是 "sqlite:///..." 字符串：项目路径含中文，
        # 字符串形式会被 SQLAlchemy 的 URL 解析破坏成乱码路径。
        app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
            "sqlite", database=(data_dir / "app.db").as_posix()
        )

    db.init_app(app)

    from app import calendar as calendar_views

    app.register_blueprint(calendar_views.bp)

    return app
