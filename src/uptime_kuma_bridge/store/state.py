"""In-memory mirror of Uptime Kuma state (task-005)."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from ..models.uk import CertInfo, Heartbeat, Monitor, ServerInfo, parse_cert_info


class StateStore:
    """Concurrency-safe store populated by the event router (task-006).

    Reads return copies so callers cannot mutate shared state. The store is
    intentionally in-memory: on restart it re-bootstraps from Uptime Kuma.
    """

    def __init__(self, heartbeat_buffer: int = 100, stale_after: float = 30.0) -> None:
        self.heartbeat_buffer = max(1, heartbeat_buffer)
        self.stale_after = stale_after
        self._lock = asyncio.Lock()

        self._monitors: dict[int, Monitor] = {}
        self._heartbeats: dict[int, deque[Heartbeat]] = {}
        self._uptime: dict[int, dict[str, float]] = {}
        self._avg_ping: dict[int, float | None] = {}
        self._cert_info: dict[int, CertInfo] = {}
        self._info: ServerInfo | None = None
        self._last_event_at: float | None = None
        self._last_heartbeat_at: dict[int, float] = {}
        self._bootstrapped = False

    # --- writers --------------------------------------------------------

    def _touch(self) -> None:
        self._last_event_at = time.time()

    async def apply_monitor_list(self, payload: dict[str, Any]) -> None:
        monitors: dict[int, Monitor] = {}
        for key, value in (payload or {}).items():
            if not isinstance(value, dict):
                continue
            data = dict(value)
            if data.get("id") is None and str(key).isdigit():
                data["id"] = int(key)
            if data.get("id") is None:
                continue
            monitor = Monitor.model_validate(data)
            monitors[monitor.id] = monitor
        async with self._lock:
            self._monitors = monitors
            self._bootstrapped = True
            self._touch()

    async def apply_monitor_update(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            for key, value in (payload or {}).items():
                if not isinstance(value, dict):
                    continue
                data = dict(value)
                if data.get("id") is None and str(key).isdigit():
                    data["id"] = int(key)
                if data.get("id") is None:
                    continue
                self._monitors[int(data["id"])] = Monitor.model_validate(data)
            self._touch()

    async def apply_monitor_delete(self, monitor_id: int) -> None:
        async with self._lock:
            self._monitors.pop(monitor_id, None)
            self._heartbeats.pop(monitor_id, None)
            self._uptime.pop(monitor_id, None)
            self._avg_ping.pop(monitor_id, None)
            self._cert_info.pop(monitor_id, None)
            self._last_heartbeat_at.pop(monitor_id, None)
            self._touch()

    async def apply_heartbeat(self, payload: dict[str, Any]) -> None:
        heartbeat = Heartbeat.model_validate(payload)
        monitor_id = heartbeat.monitor_id
        if monitor_id is None:
            return
        heartbeat = heartbeat.model_copy(update={"received_at": time.time()})
        async with self._lock:
            buffer = self._heartbeats.setdefault(monitor_id, deque(maxlen=self.heartbeat_buffer))
            buffer.append(heartbeat)
            self._last_heartbeat_at[monitor_id] = heartbeat.received_at or time.time()
            self._touch()

    async def apply_uptime(self, monitor_id: int, period: str, percentage: float) -> None:
        async with self._lock:
            self._uptime.setdefault(monitor_id, {})[str(period)] = float(percentage)
            self._touch()

    async def apply_avg_ping(self, monitor_id: int, value: float | None) -> None:
        async with self._lock:
            self._avg_ping[monitor_id] = None if value is None else float(value)
            self._touch()

    async def apply_cert_info(self, monitor_id: int, raw: Any) -> None:
        cert = parse_cert_info(raw)
        async with self._lock:
            if cert is not None:
                self._cert_info[monitor_id] = cert
            else:
                self._cert_info.pop(monitor_id, None)
            self._touch()

    async def apply_info(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            self._info = ServerInfo.model_validate(payload or {})
            self._touch()

    # --- readers --------------------------------------------------------

    async def list_monitors(self) -> list[Monitor]:
        async with self._lock:
            return [m.model_copy(deep=True) for m in self._monitors.values()]

    async def get_monitor(self, monitor_id: int) -> Monitor | None:
        async with self._lock:
            monitor = self._monitors.get(monitor_id)
            return monitor.model_copy(deep=True) if monitor else None

    async def monitor_exists(self, monitor_id: int) -> bool:
        async with self._lock:
            return monitor_id in self._monitors

    async def heartbeats(self, monitor_id: int, limit: int | None = None) -> list[Heartbeat]:
        async with self._lock:
            buffer = self._heartbeats.get(monitor_id)
            if not buffer:
                return []
            items = list(buffer)
        if limit is not None and limit > 0:
            items = items[-limit:]
        return [hb.model_copy(deep=True) for hb in items]

    async def latest_heartbeat(self, monitor_id: int) -> Heartbeat | None:
        async with self._lock:
            buffer = self._heartbeats.get(monitor_id)
            if not buffer:
                return None
            return buffer[-1].model_copy(deep=True)

    async def uptime(self, monitor_id: int) -> dict[str, float]:
        async with self._lock:
            return dict(self._uptime.get(monitor_id, {}))

    async def avg_ping(self, monitor_id: int) -> float | None:
        async with self._lock:
            return self._avg_ping.get(monitor_id)

    async def cert_info(self, monitor_id: int) -> CertInfo | None:
        async with self._lock:
            cert = self._cert_info.get(monitor_id)
            return cert.model_copy(deep=True) if cert else None

    async def server_info(self) -> ServerInfo | None:
        async with self._lock:
            return self._info.model_copy(deep=True) if self._info else None

    async def last_heartbeat_at(self, monitor_id: int) -> float | None:
        async with self._lock:
            return self._last_heartbeat_at.get(monitor_id)

    @property
    def bootstrapped(self) -> bool:
        return self._bootstrapped

    def last_event_age(self) -> float | None:
        if self._last_event_at is None:
            return None
        return max(0.0, time.time() - self._last_event_at)

    def is_stale(self) -> bool:
        age = self.last_event_age()
        return age is None or age > self.stale_after
