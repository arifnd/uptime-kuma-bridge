"""Shared test fixtures and a fake Uptime Kuma socket client."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx2
import pytest
import pytest_asyncio

from uptime_kuma_bridge.app import create_app
from uptime_kuma_bridge.config import Settings
from uptime_kuma_bridge.runtime import BridgeRuntime, RuntimeState
from uptime_kuma_bridge.uk.client import ClientState


class FakeUKClient:
    """In-process stand-in for :class:`UKSocketClient`."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Awaitable[None]]]] = defaultdict(list)
        self.state = ClientState.disconnected
        self.connected = False
        self.acks: dict[str, Any] = {}
        self.emitted: list[tuple[str, tuple[Any, ...]]] = []
        self.connect_error: Exception | None = None
        self._connected = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._disconnected.set()

    def on(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        self._handlers[event].append(handler)

    async def connect(self) -> None:
        if self.connect_error:
            raise self.connect_error
        self.connected = True
        self.state = ClientState.connecting
        self._connected.set()
        self._disconnected.clear()

    async def disconnect(self) -> None:
        self.connected = False
        self.state = ClientState.disconnected
        self._connected.clear()
        self._disconnected.set()

    async def wait_connected(self, timeout: float | None = None) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout)

    async def wait_disconnected(self) -> None:
        await self._disconnected.wait()

    async def emit_ack(self, event: str, *args: Any, timeout: float = 10.0) -> Any:
        self.emitted.append((event, args))
        value = self.acks.get(event)
        if callable(value):
            return value(*args)
        if value is not None:
            return value
        return {"ok": True}

    async def dispatch(self, event: str, *args: Any) -> None:
        for handler in list(self._handlers.get(event, [])):
            await handler(*args)


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "uk_base_url": "http://localhost:3001",
        "uk_username": "admin",
        "uk_password": "secret",
        "uk_connect_timeout": 2.0,
        "uk_reconnect_delay_max": 1.0,
        "bridge_allow_anonymous": True,
        "bridge_stale_after": 30.0,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def fake_client() -> FakeUKClient:
    return FakeUKClient()


@pytest.fixture
def runtime(settings: Settings, fake_client: FakeUKClient) -> BridgeRuntime:
    return BridgeRuntime(settings, client=fake_client)  # type: ignore[arg-type]


async def seed_monitor(
    runtime: BridgeRuntime,
    monitor_id: int = 1,
    *,
    name: str = "Site",
    status: int = 1,
    ping: float = 42.0,
) -> None:
    await runtime.store.apply_monitor_list(
        {
            str(monitor_id): {
                "id": monitor_id,
                "name": name,
                "type": "http",
                "url": "https://example.com",
                "active": True,
            }
        }
    )
    await runtime.store.apply_heartbeat(
        {
            "monitorID": monitor_id,
            "status": status,
            "msg": "OK" if status == 1 else "Down",
            "ping": ping,
            "time": "2026-01-01T00:00:00Z",
            "important": True,
        }
    )
    await runtime.store.apply_uptime(monitor_id, "24", 0.99)
    await runtime.store.apply_avg_ping(monitor_id, 50.0)
    runtime.state = RuntimeState.ready


@pytest_asyncio.fixture
async def api_client(
    runtime: BridgeRuntime,
) -> AsyncIterator[httpx2.AsyncClient]:
    app = create_app(runtime.settings, runtime)
    app.state.runtime = runtime
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
