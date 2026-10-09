"""Public REST request/response schemas (task-007)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .uk import MonitorStatus


class MonitorSummary(BaseModel):
    id: int
    name: str
    type: str
    url: str | None = None
    active: bool = True
    status: MonitorStatus = MonitorStatus.unknown
    ping: float | None = None
    uptime_24h: float | None = None
    last_heartbeat_at: str | None = None
    stale: bool = False


class MonitorDetail(MonitorSummary):
    method: str | None = None
    interval: int | None = None
    retry_interval: int | None = None
    hostname: str | None = None
    port: int | None = None
    tags: list[dict[str, Any]] = Field(default_factory=list)
    accepted_statuscodes: list[str] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class HeartbeatDTO(BaseModel):
    monitor_id: int
    status: MonitorStatus
    time: str | None = None
    msg: str | None = None
    ping: float | None = None
    important: bool = False
    duration: float | None = None
    retries: int | None = None
    received_at: float | None = None


class UptimeDTO(BaseModel):
    monitor_id: int
    period: str
    percentage: float | None = None


class PingDTO(BaseModel):
    monitor_id: int
    current: float | None = None
    average: float | None = None


class CertDTO(BaseModel):
    monitor_id: int
    valid: bool | None = None
    days_remaining: int | None = None
    issuer: dict[str, Any] | None = None
    subject: dict[str, Any] | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    authorization_error: str | None = None


class StatusDTO(BaseModel):
    id: int
    name: str
    status: MonitorStatus
    last_heartbeat_at: str | None = None
    stale: bool = False


class ServerInfoDTO(BaseModel):
    version: str | None = None
    latest_version: str | None = None
    primary_base_url: str | None = None
    server_timezone: str | None = None


class ListResponse[T](BaseModel):
    items: list[T]
    count: int


class ItemResponse[T](BaseModel):
    data: T


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | None = None
    retriable: bool = False


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ReadinessResponse(BaseModel):
    status: str
    bridge_version: str
    uptime_s: float
    bootstrapped: bool
    last_event_age_s: float | None = None
    uk_version: str | None = None


class MonitorCreate(BaseModel):
    """Create payload mapped to Uptime Kuma's ``add`` event."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    url: str | None = None
    method: str | None = None
    interval: int | None = None
    retry_interval: int | None = None
    maxretries: int | None = None
    hostname: str | None = None
    port: int | None = None
    active: bool = True

    def to_uk(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class MonitorUpdate(MonitorCreate):
    """Update payload mapped to Uptime Kuma's ``editMonitor`` event."""


class MonitorCreated(BaseModel):
    monitor_id: int | None = None


class OperationResult(BaseModel):
    ok: bool = True
