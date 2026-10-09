"""Converters between internal UK models and public DTOs (task-007)."""

from __future__ import annotations

from typing import Any

from .schemas import (
    CertDTO,
    HeartbeatDTO,
    MonitorDetail,
    MonitorSummary,
    ServerInfoDTO,
)
from .uk import (
    CertInfo,
    Heartbeat,
    Monitor,
    MonitorStatus,
    ServerInfo,
    status_from_code,
)


def heartbeat_to_dto(hb: Heartbeat, monitor_id: int | None = None) -> HeartbeatDTO:
    return HeartbeatDTO(
        monitor_id=monitor_id if monitor_id is not None else (hb.monitor_id or 0),
        status=status_from_code(hb.status),
        time=hb.time,
        msg=hb.msg,
        ping=hb.ping,
        important=hb.important,
        duration=hb.duration,
        retries=hb.retries,
        received_at=hb.received_at,
    )


def monitor_to_summary(
    monitor: Monitor,
    *,
    heartbeat: Heartbeat | None,
    uptime_24h: float | None,
    stale: bool,
) -> MonitorSummary:
    return MonitorSummary(
        id=monitor.id,
        name=monitor.name,
        type=monitor.type,
        url=monitor.url,
        active=monitor.active,
        status=status_from_code(heartbeat.status) if heartbeat else MonitorStatus.unknown,
        ping=heartbeat.ping if heartbeat else None,
        uptime_24h=uptime_24h,
        last_heartbeat_at=heartbeat.time if heartbeat else None,
        stale=stale,
    )


def monitor_to_detail(
    monitor: Monitor,
    *,
    heartbeat: Heartbeat | None,
    uptime_24h: float | None,
    stale: bool,
    raw: dict[str, Any] | None = None,
) -> MonitorDetail:
    summary = monitor_to_summary(monitor, heartbeat=heartbeat, uptime_24h=uptime_24h, stale=stale)
    return MonitorDetail(
        **summary.model_dump(),
        method=monitor.method,
        interval=monitor.interval,
        retry_interval=monitor.retry_interval,
        hostname=monitor.hostname,
        port=monitor.port,
        tags=monitor.tags,
        accepted_statuscodes=monitor.accepted_statuscodes(),
        raw=raw,
    )


def cert_to_dto(monitor_id: int, cert: CertInfo | None) -> CertDTO:
    if cert is None:
        return CertDTO(monitor_id=monitor_id)
    return CertDTO(
        monitor_id=monitor_id,
        valid=cert.valid,
        days_remaining=cert.days_remaining,
        issuer=cert.issuer,
        subject=cert.subject,
        valid_from=cert.valid_from,
        valid_to=cert.valid_to,
        authorization_error=cert.authorization_error,
    )


def server_info_to_dto(info: ServerInfo | None) -> ServerInfoDTO:
    if info is None:
        return ServerInfoDTO()
    return ServerInfoDTO(
        version=info.version,
        latest_version=info.latest_version,
        primary_base_url=info.primary_base_url,
        server_timezone=info.server_timezone,
    )
