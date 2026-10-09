"""Internal, tolerant models for Uptime Kuma payloads (task-007)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MonitorStatus(StrEnum):
    up = "UP"
    down = "DOWN"
    pending = "PENDING"
    maintenance = "MAINTENANCE"
    unknown = "UNKNOWN"


_STATUS_BY_CODE: dict[int, MonitorStatus] = {
    0: MonitorStatus.down,
    1: MonitorStatus.up,
    2: MonitorStatus.pending,
    3: MonitorStatus.maintenance,
}


def status_from_code(code: int | None) -> MonitorStatus:
    if code is None:
        return MonitorStatus.unknown
    return _STATUS_BY_CODE.get(int(code), MonitorStatus.unknown)


class _UKBase(BaseModel):
    """Tolerate fields Uptime Kuma may add or rename."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class UUIDTag(_UKBase):
    tag_id: int | None = Field(default=None, alias="tag_id")
    monitor_id: int | None = Field(default=None, alias="monitor_id")
    value: str | None = None
    name: str | None = None
    color: str | None = None


class Monitor(_UKBase):
    id: int
    name: str = ""
    type: str = ""
    url: str | None = None
    method: str | None = None
    interval: int | None = None
    retry_interval: int | None = Field(default=None, alias="retryInterval")
    resend_interval: int | None = Field(default=None, alias="resendInterval")
    maxretries: int | None = None
    hostname: str | None = None
    port: int | None = None
    active: bool = True
    tags: list[dict[str, Any]] = Field(default_factory=list)
    notification_id_list: dict[str, Any] = Field(default_factory=dict, alias="notificationIDList")
    accepted_statuscodes_json: str = Field(default="[]", alias="accepted_statuscodes_json")

    def accepted_statuscodes(self) -> list[str]:
        import json

        try:
            value = json.loads(self.accepted_statuscodes_json)
        except (TypeError, ValueError):
            return []
        return [str(v) for v in value] if isinstance(value, list) else []


class Heartbeat(_UKBase):
    monitor_id: int | None = Field(default=None, alias="monitorID")
    status: int = 0
    time: str | None = None
    msg: str | None = None
    ping: float | None = None
    important: bool = False
    duration: float | None = None
    local_date_time: str | None = Field(default=None, alias="localDateTime")
    timezone: str | None = None
    retries: int | None = None
    down_count: int | None = Field(default=None, alias="downCount")
    # Bridge bookkeeping, not sent by Uptime Kuma.
    received_at: float | None = None


class CertInfo(_UKBase):
    valid: bool | None = None
    days_remaining: int | None = Field(default=None, alias="daysRemaining")
    issuer: dict[str, Any] | None = None
    subject: dict[str, Any] | None = None
    valid_from: str | None = Field(default=None, alias="valid_from")
    valid_to: str | None = Field(default=None, alias="valid_to")
    authorization_error: str | None = Field(default=None, alias="authorizationError")


class ServerInfo(_UKBase):
    version: str | None = None
    latest_version: str | None = Field(default=None, alias="latestVersion")
    primary_base_url: str | None = Field(default=None, alias="primaryBaseURL")
    server_timezone: str | None = Field(default=None, alias="serverTimezone")


def parse_cert_info(raw: Any) -> CertInfo | None:
    """Parse ``certInfo`` / ``tlsInfoJSON`` payloads defensively."""
    import json

    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if not isinstance(raw, dict):
        return None
    # Uptime Kuma sometimes nests the certificate under "certInfo".
    nested = raw.get("certInfo")
    inner = nested if isinstance(nested, dict) else raw
    data: dict[str, Any] = dict(inner)
    if "authorizationError" in raw:
        data.setdefault("authorizationError", raw["authorizationError"])
    if data.get("valid") is None and data.get("valid_to"):
        import datetime as _dt

        try:
            valid_to = _dt.datetime.fromisoformat(str(data["valid_to"]).replace("Z", "+00:00"))
            now = _dt.datetime.now(_dt.UTC)
            if valid_to.tzinfo is None:
                valid_to = valid_to.replace(tzinfo=_dt.UTC)
            days = (valid_to - now).days
            data["daysRemaining"] = days
            data["valid"] = days >= 0
        except (TypeError, ValueError):
            pass
    return CertInfo.model_validate(data)
