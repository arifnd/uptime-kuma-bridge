"""Write REST endpoints backed by Socket.IO commands (task-009)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from ..errors import MonitorNotFoundError, NotReadyError
from ..models.schemas import (
    ItemResponse,
    MonitorCreate,
    MonitorCreated,
    MonitorUpdate,
    OperationResult,
)
from ..runtime import BridgeRuntime, RuntimeState
from .deps import get_runtime, make_auth_dependency

router = APIRouter(
    prefix="/v1",
    tags=["write"],
    dependencies=[Depends(make_auth_dependency("write"))],
)


def _ensure_ready(runtime: BridgeRuntime) -> None:
    if runtime.state is not RuntimeState.ready:
        raise NotReadyError("The bridge is not connected or authenticated to Uptime Kuma")


async def _ensure_exists(runtime: BridgeRuntime, monitor_id: int) -> None:
    if not await runtime.store.monitor_exists(monitor_id):
        raise MonitorNotFoundError(f"Monitor {monitor_id} was not found")


@router.post(
    "/monitors",
    response_model=ItemResponse[MonitorCreated],
    status_code=status.HTTP_201_CREATED,
)
async def add_monitor(
    payload: MonitorCreate,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
):
    _ensure_ready(runtime)
    monitor_id = await runtime.commands.add_monitor(payload.to_uk())
    return ItemResponse(data=MonitorCreated(monitor_id=monitor_id))


@router.put("/monitors/{monitor_id}", response_model=ItemResponse[OperationResult])
async def edit_monitor(
    monitor_id: int,
    payload: MonitorUpdate,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
):
    _ensure_ready(runtime)
    await _ensure_exists(runtime, monitor_id)
    monitor = payload.to_uk()
    monitor["id"] = monitor_id
    await runtime.commands.edit_monitor(monitor)
    return ItemResponse(data=OperationResult())


@router.delete("/monitors/{monitor_id}", response_model=ItemResponse[OperationResult])
async def delete_monitor(
    monitor_id: int,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
):
    _ensure_ready(runtime)
    await _ensure_exists(runtime, monitor_id)
    await runtime.commands.delete_monitor(monitor_id)
    return ItemResponse(data=OperationResult())


@router.post("/monitors/{monitor_id}/pause", response_model=ItemResponse[OperationResult])
async def pause_monitor(
    monitor_id: int,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
):
    _ensure_ready(runtime)
    await _ensure_exists(runtime, monitor_id)
    await runtime.commands.pause_monitor(monitor_id)
    return ItemResponse(data=OperationResult())


@router.post("/monitors/{monitor_id}/resume", response_model=ItemResponse[OperationResult])
async def resume_monitor(
    monitor_id: int,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
):
    _ensure_ready(runtime)
    await _ensure_exists(runtime, monitor_id)
    await runtime.commands.resume_monitor(monitor_id)
    return ItemResponse(data=OperationResult())
