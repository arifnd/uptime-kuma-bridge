"""Socket.IO command service for write operations (task-009)."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import Settings
from ..errors import UKConflict, UKRejected, UpstreamError
from ..observability import metrics
from .client import UKSocketClient

logger = logging.getLogger(__name__)


class CommandService:
    """Translates REST write operations into Uptime Kuma Socket.IO commands."""

    def __init__(self, settings: Settings, client: UKSocketClient) -> None:
        self._settings = settings
        self._client = client

    async def _emit(self, event: str, *args: Any) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            result = await self._client.emit_ack(event, *args)
        finally:
            metrics.bridge_command_duration_seconds.labels(event=event).observe(
                time.perf_counter() - start
            )
        return self._check(event, result)

    def _check(self, event: str, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise UpstreamError(f"Unexpected response for {event}: {result!r}")
        if result.get("ok"):
            return result
        message = str(result.get("msg", f"Uptime Kuma rejected {event}"))
        detail = {"uk_msg": message, "msgi18n": bool(result.get("msgi18n"))}
        lowered = message.lower()
        if any(word in lowered for word in ("exist", "duplicate", "conflict", "already")):
            raise UKConflict(message, detail=detail)
        raise UKRejected(message, detail=detail)

    async def add_monitor(self, monitor: dict[str, Any]) -> int | None:
        result = await self._emit("add", monitor)
        monitor_id = result.get("monitorID")
        return int(monitor_id) if monitor_id is not None else None

    async def edit_monitor(self, monitor: dict[str, Any]) -> None:
        await self._emit("editMonitor", monitor)

    async def delete_monitor(self, monitor_id: int) -> None:
        await self._emit("deleteMonitor", monitor_id)

    async def pause_monitor(self, monitor_id: int) -> None:
        await self._emit("pauseMonitor", monitor_id)

    async def resume_monitor(self, monitor_id: int) -> None:
        await self._emit("resumeMonitor", monitor_id)

    async def get_monitor_beats(self, monitor_id: int, period: int) -> list[dict[str, Any]]:
        result = await self._emit("getMonitorBeats", monitor_id, period)
        data = result.get("data")
        return data if isinstance(data, list) else []
