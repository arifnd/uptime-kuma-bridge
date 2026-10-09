"""Real-time event ingestion, normalization and pub/sub (task-006)."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from ..observability import metrics
from ..store.state import StateStore
from .client import UKSocketClient

logger = logging.getLogger(__name__)


@dataclass
class Event:
    seq: int
    event: str
    data: dict[str, Any]
    ts: float


class Subscription:
    """A bounded, drop-oldest queue delivered to one HTTP/WS consumer."""

    def __init__(
        self,
        monitor_ids: set[int] | None = None,
        events: set[str] | None = None,
        maxsize: int = 100,
    ) -> None:
        self.monitor_ids = monitor_ids or None
        self.events = events or None
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def matches(self, event: Event) -> bool:
        if self.events is not None and event.event not in self.events:
            return False
        if self.monitor_ids is not None:
            monitor_id = event.data.get("monitor_id")
            if monitor_id is not None and monitor_id not in self.monitor_ids:
                return False
            if monitor_id is None and event.event != "monitorList":
                return False
        return True

    def offer(self, event: Event) -> None:
        if self.queue.full():
            self.dropped += 1
            with suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover - defensive
            self.dropped += 1

    async def get(self) -> Event:
        return await self.queue.get()


class EventBus:
    """In-process fan-out of normalized events to stream consumers."""

    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()
        self._seq = 0

    def subscribe(
        self,
        monitor_ids: set[int] | None = None,
        events: set[str] | None = None,
    ) -> Subscription:
        subscription = Subscription(monitor_ids=monitor_ids, events=events)
        self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscriptions.discard(subscription)

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        self._seq += 1
        payload = Event(seq=self._seq, event=event, data=data, ts=time.time())
        for subscription in list(self._subscriptions):
            if subscription.matches(payload):
                subscription.offer(payload)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscriptions)


class EventRouter:
    """Maps Uptime Kuma server events onto store mutations and the event bus."""

    SERVER_EVENTS = (
        "monitorList",
        "updateMonitorIntoList",
        "deleteMonitorFromList",
        "heartbeat",
        "uptime",
        "avgPing",
        "certInfo",
        "info",
    )

    def __init__(self, store: StateStore, bus: EventBus, client: UKSocketClient) -> None:
        self._store = store
        self._bus = bus
        self._client = client
        self._registered = False

    def register(self) -> None:
        if self._registered:
            return
        self._client.on("monitorList", self._wrap("monitorList", self._on_monitor_list))
        self._client.on(
            "updateMonitorIntoList",
            self._wrap("updateMonitorIntoList", self._on_monitor_update),
        )
        self._client.on(
            "deleteMonitorFromList",
            self._wrap("deleteMonitorFromList", self._on_monitor_delete),
        )
        self._client.on("heartbeat", self._wrap("heartbeat", self._on_heartbeat))
        self._client.on("uptime", self._wrap("uptime", self._on_uptime))
        self._client.on("avgPing", self._wrap("avgPing", self._on_avg_ping))
        self._client.on("certInfo", self._wrap("certInfo", self._on_cert_info))
        self._client.on("info", self._wrap("info", self._on_info))
        self._registered = True

    def _wrap(self, name: str, handler: Any) -> Any:
        async def wrapped(*args: Any, **kwargs: Any) -> None:
            metrics.uk_events_total.labels(event=name).inc()
            try:
                await handler(*args, **kwargs)
            except Exception:  # noqa: BLE001 - never crash the transport loop
                metrics.uk_event_parse_errors_total.labels(event=name).inc()
                logger.warning("Failed to process %s event", name, exc_info=True)

        return wrapped

    # --- handlers -------------------------------------------------------

    async def _on_monitor_list(self, payload: Any = None) -> None:
        payload = payload if isinstance(payload, dict) else {}
        await self._store.apply_monitor_list(payload)
        await self._bus.publish(
            "monitorList",
            {"monitor_ids": sorted(str(k) for k in payload)},
        )

    async def _on_monitor_update(self, payload: Any = None) -> None:
        payload = payload if isinstance(payload, dict) else {}
        await self._store.apply_monitor_update(payload)
        await self._bus.publish(
            "monitorUpdate",
            {"monitor_ids": sorted(str(k) for k in payload)},
        )

    async def _on_monitor_delete(self, payload: Any = None) -> None:
        monitor_id = _coerce_int(payload)
        if monitor_id is None:
            raise ValueError("deleteMonitorFromList without a monitor id")
        await self._store.apply_monitor_delete(monitor_id)
        await self._bus.publish("monitorDelete", {"monitor_id": monitor_id})

    async def _on_heartbeat(self, payload: Any = None) -> None:
        if not isinstance(payload, dict):
            raise ValueError("heartbeat payload is not an object")
        await self._store.apply_heartbeat(payload)
        await self._bus.publish(
            "heartbeat",
            {
                "monitor_id": _coerce_int(payload.get("monitorID")),
                "status": _coerce_int(payload.get("status")),
                "msg": payload.get("msg"),
                "ping": payload.get("ping"),
                "time": payload.get("time"),
            },
        )

    async def _on_uptime(self, *args: Any) -> None:
        monitor_id, period, percentage = _parse_uptime(args)
        if monitor_id is None or period is None or percentage is None:
            raise ValueError(f"Malformed uptime event: {args!r}")
        await self._store.apply_uptime(monitor_id, period, float(percentage))
        await self._bus.publish(
            "uptime",
            {
                "monitor_id": monitor_id,
                "period": period,
                "percentage": float(percentage),
            },
        )

    async def _on_avg_ping(self, *args: Any) -> None:
        monitor_id, value = _parse_avg_ping(args)
        if monitor_id is None:
            raise ValueError(f"Malformed avgPing event: {args!r}")
        await self._store.apply_avg_ping(monitor_id, value)
        await self._bus.publish("avgPing", {"monitor_id": monitor_id, "avg_ping": value})

    async def _on_cert_info(self, *args: Any) -> None:
        monitor_id, raw = _parse_cert_info(args)
        if monitor_id is None:
            raise ValueError(f"Malformed certInfo event: {args!r}")
        await self._store.apply_cert_info(monitor_id, raw)
        await self._bus.publish("certInfo", {"monitor_id": monitor_id})

    async def _on_info(self, payload: Any = None) -> None:
        payload = payload if isinstance(payload, dict) else {}
        await self._store.apply_info(payload)
        await self._bus.publish("info", {})


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_uptime(args: tuple[Any, ...]) -> tuple[int | None, str | None, float | None]:
    if len(args) == 1 and isinstance(args[0], dict):
        payload = args[0]
        return (
            _coerce_int(payload.get("monitorID")),
            str(payload.get("periodKey") or payload.get("period") or ""),
            _float_or_none(payload.get("percentage")),
        )
    if len(args) >= 3:
        return _coerce_int(args[0]), str(args[1]), _float_or_none(args[2])
    return None, None, None


def _parse_avg_ping(args: tuple[Any, ...]) -> tuple[int | None, float | None]:
    if len(args) == 1 and isinstance(args[0], dict):
        payload = args[0]
        return _coerce_int(payload.get("monitorID")), _float_or_none(payload.get("avgPing"))
    if len(args) >= 2:
        return _coerce_int(args[0]), _float_or_none(args[1])
    return None, None


def _parse_cert_info(args: tuple[Any, ...]) -> tuple[int | None, Any]:
    if len(args) == 1 and isinstance(args[0], dict):
        payload = args[0]
        return _coerce_int(payload.get("monitorID")), payload.get("tlsInfoJSON")
    if len(args) >= 2:
        return _coerce_int(args[0]), args[1]
    return None, None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
