import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy.engine import URL

from app import create_app
from app.db import db as _db

# 测试用的临时目录放在项目内：本机沙箱不允许在系统 %TEMP% 下创建数据库文件。
TMP_ROOT = Path(__file__).resolve().parent.parent / ".pytest-tmp"


@pytest.fixture
def app():
    TMP_ROOT.mkdir(exist_ok=True)
    # 不用 tempfile.mkdtemp：本机沙箱不给 mkdtemp 建出来的目录写权限。
    workdir = TMP_ROOT / f"case-{uuid.uuid4().hex[:8]}"
    workdir.mkdir()
    application = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": URL.create(
                "sqlite", database=(workdir / "t.db").as_posix()
            ),
            "TESTING": True,
        }
    )
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
    shutil.rmtree(workdir, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()
