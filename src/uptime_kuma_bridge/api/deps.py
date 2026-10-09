"""FastAPI dependencies and inbound auth (task-013)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from fastapi import Request, WebSocket

from ..config import Settings
from ..errors import ForbiddenError, UnauthorizedError
from ..runtime import BridgeRuntime


@dataclass
class AuthContext:
    scopes: set[str] = field(default_factory=set)
    key: str | None = None


def get_runtime(request: Request) -> BridgeRuntime:
    return request.app.state.runtime


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.runtime.settings


def _extract_key(headers: dict[str, str], query_key: str | None = None) -> str | None:
    if query_key:
        return query_key
    authorization = headers.get("authorization") or headers.get("Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return headers.get("x-api-key") or headers.get("X-API-Key")


def _authorize(settings: Settings, provided: str | None, required_scope: str | None) -> AuthContext:
    api_keys = settings.api_key_scopes
    if not api_keys:
        if settings.bridge_allow_anonymous:
            return AuthContext(scopes={"read", "write"})
        raise UnauthorizedError("API keys are not configured")
    if not provided:
        raise UnauthorizedError("Missing API key")
    for key, scopes in api_keys.items():
        if secrets.compare_digest(provided, key):
            if required_scope and required_scope not in scopes:
                raise ForbiddenError(f"API key lacks the '{required_scope}' scope")
            return AuthContext(scopes=scopes, key=key)
    raise UnauthorizedError("Invalid API key")


def make_auth_dependency(required_scope: str | None = None):
    async def dependency(request: Request) -> AuthContext:
        settings: Settings = request.app.state.runtime.settings
        provided = _extract_key(dict(request.headers))
        return _authorize(settings, provided, required_scope)

    return dependency


def authorize_websocket(websocket: WebSocket, required_scope: str | None = None) -> AuthContext:
    settings: Settings = websocket.app.state.runtime.settings
    provided = _extract_key(dict(websocket.headers), websocket.query_params.get("api_key"))
    return _authorize(settings, provided, required_scope)
