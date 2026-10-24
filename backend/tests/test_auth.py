"""认证与会话（HLD §12.0 auth 行、§7；SRS FR-1 / FR-2）。

覆盖点：注册成功/重复 409/用户名长度/密码 ≥6；登录成功/密码错误统一文案；
无 token 401/坏 token 401；另补过期 token、user 已删除、哈希形态与「响应不含密码」。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

import pytest
from app.core.deps import UNAUTHORIZED_DETAIL, get_current_user
from app.core.security import (
    TokenPolicy,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import User
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

USERNAME = "lifter"
PASSWORD = "secret123"
REGISTER = "/auth/register"
LOGIN = "/auth/login"


def _whoami(user: Annotated[User, Depends(get_current_user)]) -> dict[str, str]:
    """仅测试用：首个受保护端点，验证 Bearer → 当前用户这条链路。"""
    return {"username": user.username}


@pytest.fixture()
def private_client(app: FastAPI) -> Iterator[TestClient]:
    """带一个受保护探针端点的客户端（业务端点随票 08 起落地）。"""
    app.router.add_api_route("/_test/whoami", _whoami, methods=["GET"], include_in_schema=False)
    with TestClient(app) as test_client:
        yield test_client


def _register(
    client: TestClient, username: str = USERNAME, password: str = PASSWORD
) -> dict[str, Any]:
    response = client.post(REGISTER, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _token_of(body: dict[str, Any]) -> str:
    token = body["token"]
    assert isinstance(token, str) and token
    return token


def _detail_of(payload: dict[str, Any]) -> str:
    """取错误体 detail：字符串（401/409）或 422 数组首条 msg。"""
    detail = payload["detail"]
    if isinstance(detail, str):
        return detail
    assert isinstance(detail, list) and detail
    msg = detail[0]["msg"]
    assert isinstance(msg, str)
    return msg


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------- 注册 ----------


def test_register_returns_token_and_username(private_client: TestClient) -> None:
    body = _register(private_client)

    assert body["user"] == {"username": USERNAME}
    assert _token_of(body)
    assert body.keys() == {"token", "user"}  # 不回密码/哈希（SRS FR-1.2）


def test_register_strips_username_whitespace(private_client: TestClient) -> None:
    body = _register(private_client, username="  lifter  ")

    assert body["user"] == {"username": "lifter"}
    assert (
        private_client.post(LOGIN, json={"username": "lifter", "password": PASSWORD}).status_code
        == 200
    )


def test_register_duplicate_username_conflict(private_client: TestClient) -> None:
    _register(private_client)

    response = private_client.post(REGISTER, json={"username": USERNAME, "password": "another1"})

    assert response.status_code == 409
    assert _detail_of(response.json()) == "用户名已被占用"


@pytest.mark.parametrize("username", ["ab", "a" * 21, "   ", ""])
def test_register_rejects_username_out_of_length(private_client: TestClient, username: str) -> None:
    response = private_client.post(REGISTER, json={"username": username, "password": PASSWORD})

    assert response.status_code == 422
    assert "用户名长度需为 3–20 个字符" in _detail_of(response.json())


def test_register_rejects_short_password(private_client: TestClient) -> None:
    response = private_client.post(REGISTER, json={"username": USERNAME, "password": "12345"})

    assert response.status_code == 422
    assert _detail_of(response.json()) == "密码至少 6 位"


def test_register_rejects_password_over_bcrypt_limit(private_client: TestClient) -> None:
    """bcrypt 上限按字节：73 个 ASCII 字符即超限，422 而非静默截断。"""
    response = private_client.post(REGISTER, json={"username": USERNAME, "password": "a" * 73})

    assert response.status_code == 422
    assert "72" in _detail_of(response.json())


def test_register_stores_bcrypt_hash_cost_12(
    private_client: TestClient, db_session: Session
) -> None:
    _register(private_client)

    user = db_session.scalar(select(User).where(User.username == USERNAME))
    assert user is not None
    assert user.password_hash.startswith("$2b$12$")
    assert PASSWORD not in user.password_hash
    assert verify_password(PASSWORD, user.password_hash)


# ---------- 登录 ----------


def test_login_success_returns_usable_token(private_client: TestClient) -> None:
    _register(private_client)

    response = private_client.post(LOGIN, json={"username": USERNAME, "password": PASSWORD})

    assert response.status_code == 200
    token = _token_of(response.json())
    probe = private_client.get("/_test/whoami", headers=_bearer(token))
    assert probe.status_code == 200
    assert probe.json() == {"username": USERNAME}


def test_login_wrong_password_uses_unified_message(private_client: TestClient) -> None:
    _register(private_client)

    response = private_client.post(LOGIN, json={"username": USERNAME, "password": "wrongpass"})

    assert response.status_code == 401
    assert _detail_of(response.json()) == "用户名或密码不对"


def test_login_unknown_user_uses_same_message(private_client: TestClient) -> None:
    response = private_client.post(LOGIN, json={"username": "nobody", "password": PASSWORD})

    assert response.status_code == 401
    assert _detail_of(response.json()) == "用户名或密码不对"


# ---------- 鉴权依赖 ----------


def test_protected_endpoint_without_token_is_401(private_client: TestClient) -> None:
    response = private_client.get("/_test/whoami")

    assert response.status_code == 401
    assert _detail_of(response.json()) == UNAUTHORIZED_DETAIL
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "authorization",
    ["Bearer not-a-jwt", "Bearer ", "Basic bGlmdGVyOnNlY3JldA==", "garbage"],
)
def test_protected_endpoint_with_bad_token_is_401(
    private_client: TestClient, authorization: str
) -> None:
    response = private_client.get("/_test/whoami", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert _detail_of(response.json()) == UNAUTHORIZED_DETAIL


def test_protected_endpoint_with_expired_token_is_401(
    private_client: TestClient, app: FastAPI, db_session: Session
) -> None:
    token = _token_of(_register(private_client))
    user = db_session.scalar(select(User).where(User.username == USERNAME))
    assert user is not None
    policy = TokenPolicy(secret=app.state.secret_key, ttl_days=-1)
    expired = create_access_token(user.id, policy)

    response = private_client.get("/_test/whoami", headers=_bearer(expired))
    assert response.status_code == 401
    assert _detail_of(response.json()) == UNAUTHORIZED_DETAIL

    # 同一用户的有效 token 仍可通行（证明上面失败的是过期而非别的）
    assert private_client.get("/_test/whoami", headers=_bearer(token)).status_code == 200


def test_token_signed_with_other_secret_is_401(private_client: TestClient) -> None:
    forged = create_access_token(1, TokenPolicy(secret="attacker-secret-that-is-32-bytes-or-more"))

    response = private_client.get("/_test/whoami", headers=_bearer(forged))

    assert response.status_code == 401


def test_token_of_deleted_user_is_401(private_client: TestClient, db_session: Session) -> None:
    token = _token_of(_register(private_client))
    user = db_session.scalar(select(User).where(User.username == USERNAME))
    assert user is not None
    db_session.delete(user)
    db_session.commit()

    response = private_client.get("/_test/whoami", headers=_bearer(token))

    assert response.status_code == 401
    assert _detail_of(response.json()) == UNAUTHORIZED_DETAIL


# ---------- security 单元（不变量：绝不把异常漏给请求路径） ----------


def test_hash_password_is_salted_and_verifiable() -> None:
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    assert first != second
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrongpass", first)


@pytest.mark.parametrize("stored", ["", "not-a-hash", "$2b$12$broken"])
def test_verify_password_never_raises(stored: str) -> None:
    assert verify_password(PASSWORD, stored) is False


def test_hash_password_rejects_over_limit() -> None:
    with pytest.raises(ValueError):
        hash_password("a" * 73)


def test_decode_access_token_roundtrip_and_rejection() -> None:
    policy = TokenPolicy(secret="unit-secret-that-is-32-bytes-long!!")
    token = create_access_token(42, policy)
    expired = create_access_token(
        42, TokenPolicy(secret="unit-secret-that-is-32-bytes-long!!", ttl_days=-1)
    )

    assert decode_access_token(token, policy) == 42
    assert (
        decode_access_token(token, TokenPolicy(secret="other-secret-that-is-also-long-enough!"))
        is None
    )
    assert decode_access_token("not-a-jwt", policy) is None
    assert decode_access_token(expired, policy) is None
