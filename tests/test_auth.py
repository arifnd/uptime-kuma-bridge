"""Authentication flow tests (task-004)."""

from __future__ import annotations

import pytest

from uptime_kuma_bridge.errors import AuthFailed, TwoFactorRequired
from uptime_kuma_bridge.uk.auth import Authenticator, TokenStore

from .conftest import FakeUKClient, make_settings


async def test_login_by_token_success() -> None:
    client = FakeUKClient()
    settings = make_settings(uk_jwt_token="good-token")
    client.acks["loginByToken"] = {"ok": True}
    auth = Authenticator(settings, client)  # type: ignore[arg-type]
    await auth.authenticate()
    assert auth.method == "loginByToken"
    assert client.emitted[0][0] == "loginByToken"


async def test_invalid_token_falls_back_to_password() -> None:
    client = FakeUKClient()
    settings = make_settings(uk_jwt_token="stale")
    client.acks["loginByToken"] = {"ok": False, "msg": "invalid"}
    client.acks["login"] = {"ok": True, "token": "fresh"}
    tokens = TokenStore()
    auth = Authenticator(settings, client, token_store=tokens)  # type: ignore[arg-type]
    await auth.authenticate()
    assert auth.method == "login"
    assert tokens.get() == "fresh"


async def test_two_factor_required() -> None:
    client = FakeUKClient()
    settings = make_settings()
    client.acks["login"] = {"ok": False, "tokenRequired": True}
    auth = Authenticator(settings, client)  # type: ignore[arg-type]
    with pytest.raises(TwoFactorRequired):
        await auth.authenticate()


async def test_login_failure() -> None:
    client = FakeUKClient()
    settings = make_settings()
    client.acks["login"] = {"ok": False, "msg": "bad credentials"}
    auth = Authenticator(settings, client)  # type: ignore[arg-type]
    with pytest.raises(AuthFailed):
        await auth.authenticate()


async def test_token_store_persists_file(tmp_path) -> None:
    path = tmp_path / "token"
    store = TokenStore(str(path))
    assert store.get() is None
    store.set("abc")
    assert store.get() == "abc"
    assert TokenStore(str(path)).get() == "abc"
