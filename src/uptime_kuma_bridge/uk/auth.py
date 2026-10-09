"""Authentication flow against Uptime Kuma (task-004)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ..config import Settings
from ..errors import AuthFailed, TwoFactorRequired, UpstreamError
from .client import UKSocketClient

logger = logging.getLogger(__name__)


class TokenStore:
    """In-memory JWT cache with optional 0600 file persistence."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path
        self._token: str | None = None
        if path and os.path.exists(path):
            try:
                self._token = Path(path).read_text(encoding="utf-8").strip() or None
            except OSError:
                logger.warning("Could not read token file %s", path)

    def get(self) -> str | None:
        return self._token

    def set(self, token: str | None) -> None:
        self._token = token
        if self._path and token:
            try:
                Path(self._path).write_text(token, encoding="utf-8")
                os.chmod(self._path, 0o600)
            except OSError:
                logger.warning("Could not persist token file %s", self._path)


class Authenticator:
    """Authenticates a connected socket using a JWT or username/password."""

    def __init__(
        self,
        settings: Settings,
        client: UKSocketClient,
        token_store: TokenStore | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._tokens = token_store or TokenStore(settings.uk_token_file)
        self.method: str | None = None

    async def authenticate(self) -> None:
        token = self._configured_token() or self._tokens.get()
        if token:
            try:
                result = await self._client.emit_ack("loginByToken", token)
            except UpstreamError as exc:
                logger.warning("loginByToken transport error: %s", exc)
                result = None
            if isinstance(result, dict) and result.get("ok"):
                self.method = "loginByToken"
                self._tokens.set(token)
                return
            logger.warning("loginByToken rejected (%s); falling back to password", result)
        await self._login()

    def _configured_token(self) -> str | None:
        if self._settings.uk_jwt_token:
            return self._settings.uk_jwt_token.get_secret_value()
        return None

    async def _login(self) -> None:
        settings = self._settings
        if not (settings.uk_username and settings.uk_password):
            raise AuthFailed("No authentication credentials are configured")
        payload: dict[str, str] = {
            "username": settings.uk_username,
            "password": settings.uk_password.get_secret_value(),
        }
        if settings.uk_2fa_token:
            payload["token"] = settings.uk_2fa_token.get_secret_value()

        result = await self._client.emit_ack("login", payload)
        if not isinstance(result, dict) or not result.get("ok"):
            result = result if isinstance(result, dict) else {}
            if result.get("tokenRequired"):
                raise TwoFactorRequired("Uptime Kuma requires a 2FA token")
            raise AuthFailed(str(result.get("msg", "login failed")))
        if result.get("token"):
            self._tokens.set(str(result["token"]))
        self.method = "login"
