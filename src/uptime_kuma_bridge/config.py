"""Environment-driven configuration (task-002)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str) -> list[str]:
    """Split a comma-separated string, tolerating JSON-ish surrounding syntax."""
    value = value.strip()
    if not value:
        return []
    for ch in "[]\"'":
        value = value.replace(ch, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_api_keys(value: str) -> dict[str, set[str]]:
    """Parse ``key`` / ``key:r`` / ``key:rw`` entries into a scope map."""
    keys: dict[str, set[str]] = {}
    for item in _split_csv(value):
        key, _, scope = item.partition(":")
        key = key.strip()
        if not key:
            continue
        scopes: set[str] = set()
        for ch in (scope or "rw").strip().lower():
            if ch == "r":
                scopes.add("read")
            elif ch == "w":
                scopes.add("write")
        keys[key] = scopes or {"read", "write"}
    return keys


class Settings(BaseSettings):
    """Validated bridge configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Uptime Kuma connection
    uk_base_url: str = "http://localhost:3001"
    uk_username: str | None = None
    uk_password: SecretStr | None = None
    uk_jwt_token: SecretStr | None = None
    uk_2fa_token: SecretStr | None = None
    uk_token_file: str | None = None
    uk_connect_timeout: float = 10.0
    uk_reconnect_delay_max: float = 30.0
    uk_verify_tls: bool = True
    uk_socketio_path: str = "socket.io"

    # Bridge API
    bridge_api_keys: str = ""
    bridge_cors_origins: str = ""
    bridge_allow_anonymous: bool = True
    bridge_stale_after: float = 30.0
    bridge_heartbeat_buffer: int = 100

    # Misc
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _validate_auth(self) -> Settings:
        has_token = self.uk_jwt_token is not None
        has_credentials = bool(self.uk_username and self.uk_password)
        if not has_token and not has_credentials:
            raise ValueError(
                "Authentication is not configured: set UK_JWT_TOKEN, or both "
                "UK_USERNAME and UK_PASSWORD."
            )
        return self

    @model_validator(mode="after")
    def _validate_keys(self) -> Settings:
        if not self.bridge_api_keys and not self.bridge_allow_anonymous:
            raise ValueError(
                "No BRIDGE_API_KEYS configured and BRIDGE_ALLOW_ANONYMOUS is "
                "false: refusing to start an unauthenticated bridge."
            )
        return self

    # --- Derived values -------------------------------------------------

    @property
    def socketio_url(self) -> str:
        """Base URL used for the Socket.IO connection (trailing slash trimmed)."""
        return self.uk_base_url.rstrip("/")

    @property
    def socketio_path(self) -> str:
        return self.uk_socketio_path.strip("/")

    @property
    def api_key_scopes(self) -> dict[str, set[str]]:
        return parse_api_keys(self.bridge_api_keys)

    @property
    def cors_origins(self) -> list[str]:
        return _split_csv(self.bridge_cors_origins)

    @property
    def secret_values(self) -> list[str]:
        """All configured secret strings, for log redaction."""
        secrets_: list[str] = []
        for field in (self.uk_password, self.uk_jwt_token, self.uk_2fa_token):
            if isinstance(field, SecretStr):
                value = field.get_secret_value()
                if value:
                    secrets_.append(value)
        return secrets_


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
