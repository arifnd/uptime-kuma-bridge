"""Read-only REST endpoints (task-008)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..errors import MonitorNotFoundError
from ..models.convert import (
    cert_to_dto,
    heartbeat_to_dto,
    monitor_to_detail,
    monitor_to_summary,
)
from ..models.schemas import (
    CertDTO,
    HeartbeatDTO,
    ListResponse,
    MonitorDetail,
    MonitorSummary,
    PingDTO,
    StatusDTO,
    UptimeDTO,
)
from ..models.uk import Heartbeat, status_from_code
from ..runtime import BridgeRuntime
from .deps import get_runtime, make_auth_dependency

router = APIRouter(
    prefix="/v1",
    tags=["read"],
    dependencies=[Depends(make_auth_dependency("read"))],
)

_PERIOD_CANDIDATES: dict[str, list[str]] = {
    "24h": ["24", "24h", "1_24"],
    "7d": ["168", "7d", "168h", "1_168"],
    "30d": ["720", "30d", "720h", "1_720"],
    "1y": ["8760", "1y", "365d", "8760h", "1_8760"],
}


def _lookup_period(uptime_map: dict[str, float], period: str) -> float | None:
    if period in uptime_map:
        return uptime_map[period]
    for candidate in _PERIOD_CANDIDATES.get(period, []):
        if candidate in uptime_map:
            return uptime_map[candidate]
    return None


@router.get("/monitors", response_model=ListResponse[MonitorSummary])
async def list_monitors(runtime: Annotated[BridgeRuntime, Depends(get_runtime)]):
    monitors = await runtime.store.list_monitors()
    stale = runtime.store.is_stale()
    items: list[MonitorSummary] = []
    for monitor in monitors:
        heartbeat = await runtime.store.latest_heartbeat(monitor.id)
        uptime_map = await runtime.store.uptime(monitor.id)
        items.append(
            monitor_to_summary(
                monitor,
                heartbeat=heartbeat,
                uptime_24h=_lookup_period(uptime_map, "24h"),
                stale=stale,
            )
        )
    return ListResponse(items=items, count=len(items))


@router.get("/status", response_model=ListResponse[StatusDTO])
async def list_status(runtime: Annotated[BridgeRuntime, Depends(get_runtime)]):
    monitors = await runtime.store.list_monitors()
    stale = runtime.store.is_stale()
    items: list[StatusDTO] = []
    for monitor in monitors:
        heartbeat = await runtime.store.latest_heartbeat(monitor.id)
        items.append(
            StatusDTO(
                id=monitor.id,
                name=monitor.name,
                status=status_from_code(heartbeat.status) if heartbeat else status_from_code(None),
                last_heartbeat_at=heartbeat.time if heartbeat else None,
                stale=stale,
            )
        )
    return ListResponse(items=items, count=len(items))


@router.get("/monitors/{monitor_id}", response_model=MonitorDetail)
async def get_monitor(
    monitor_id: int,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
    include: Annotated[str | None, Query()] = None,
):
    monitor = await runtime.store.get_monitor(monitor_id)
    if monitor is None:
        raise MonitorNotFoundError(f"Monitor {monitor_id} was not found")
    heartbeat = await runtime.store.latest_heartbeat(monitor_id)
    uptime_map = await runtime.store.uptime(monitor_id)
    raw = monitor.model_dump() if include and "raw" in include else None
    return monitor_to_detail(
        monitor,
        heartbeat=heartbeat,
        uptime_24h=_lookup_period(uptime_map, "24h"),
        stale=runtime.store.is_stale(),
        raw=raw,
    )


@router.get("/monitors/{monitor_id}/heartbeats", response_model=ListResponse[HeartbeatDTO])
async def get_heartbeats(
    monitor_id: int,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    period: Annotated[int, Query(ge=1, le=8760)] = 24,
):
    if not await runtime.store.monitor_exists(monitor_id):
        raise MonitorNotFoundError(f"Monitor {monitor_id} was not found")
    heartbeats: list[Heartbeat] = await runtime.store.heartbeats(monitor_id, limit=limit)
    if not heartbeats and runtime.ready:
        raw_beats = await runtime.commands.get_monitor_beats(monitor_id, period)
        heartbeats = [Heartbeat.model_validate(beat) for beat in raw_beats][-limit:]
    items = [heartbeat_to_dto(hb, monitor_id) for hb in heartbeats]
    return ListResponse(items=items, count=len(items))


@router.get("/monitors/{monitor_id}/uptime", response_model=UptimeDTO)
async def get_uptime(
    monitor_id: int,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
    period: Annotated[str, Query(pattern="^(24h|7d|30d|1y)$")] = "24h",
):
    if not await runtime.store.monitor_exists(monitor_id):
        raise MonitorNotFoundError(f"Monitor {monitor_id} was not found")
    uptime_map = await runtime.store.uptime(monitor_id)
    return UptimeDTO(
        monitor_id=monitor_id,
        period=period,
        percentage=_lookup_period(uptime_map, period),
    )


@router.get("/monitors/{monitor_id}/ping", response_model=PingDTO)
async def get_ping(
    monitor_id: int,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
):
    if not await runtime.store.monitor_exists(monitor_id):
        raise MonitorNotFoundError(f"Monitor {monitor_id} was not found")
    heartbeat = await runtime.store.latest_heartbeat(monitor_id)
    average = await runtime.store.avg_ping(monitor_id)
    return PingDTO(
        monitor_id=monitor_id,
        current=heartbeat.ping if heartbeat else None,
        average=average,
    )


@router.get("/monitors/{monitor_id}/cert", response_model=CertDTO)
async def get_cert(
    monitor_id: int,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
):
    if not await runtime.store.monitor_exists(monitor_id):
        raise MonitorNotFoundError(f"Monitor {monitor_id} was not found")
    cert = await runtime.store.cert_info(monitor_id)
    return cert_to_dto(monitor_id, cert)
