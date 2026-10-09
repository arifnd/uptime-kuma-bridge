"""Configuration tests (task-002)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from uptime_kuma_bridge.config import Settings, parse_api_keys


def test_requires_some_auth() -> None:
    with pytest.raises(ValidationError):
        Settings(uk_base_url="http://localhost:3001")


def test_username_password_auth() -> None:
    settings = Settings(uk_username="admin", uk_password="secret")
    assert settings.socketio_url == "http://localhost:3001"
    assert settings.socketio_path == "socket.io"


def test_jwt_only_auth() -> None:
    settings = Settings(uk_jwt_token="tok")
    assert settings.uk_username is None


def test_secrets_are_redacted_in_repr() -> None:
    settings = Settings(uk_username="admin", uk_password="supersecret")
    assert "supersecret" not in repr(settings)
    assert "supersecret" in settings.secret_values


def test_base_url_trailing_slash_trimmed() -> None:
    settings = Settings(uk_username="a", uk_password="b", uk_base_url="http://kuma:3001/")
    assert settings.socketio_url == "http://kuma:3001"


def test_parse_api_key_scopes() -> None:
    parsed = parse_api_keys("abc,def:r,ghi:rw")
    assert parsed["abc"] == {"read", "write"}
    assert parsed["def"] == {"read"}
    assert parsed["ghi"] == {"read", "write"}


def test_cors_origins_jsonish() -> None:
    settings = Settings(
        uk_username="a",
        uk_password="b",
        bridge_cors_origins='["https://a.example", "https://b.example"]',
    )
    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_anonymous_forbidden_without_keys() -> None:
    with pytest.raises(ValidationError):
        Settings(
            uk_username="a",
            uk_password="b",
            bridge_allow_anonymous=False,
        )
