"""End-to-end test against a real in-process Socket.IO server (task-015)."""

from __future__ import annotations

import asyncio

import httpx2
import pytest

from uptime_kuma_bridge.app import create_app
from uptime_kuma_bridge.config import Settings
from uptime_kuma_bridge.runtime import BridgeRuntime, RuntimeState

from .fake_uk import FakeUKServer


async def _wait_until(condition, timeout: float = 10.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if condition():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not met within timeout")


@pytest.mark.integration
async def test_full_stack_connect_auth_read_write() -> None:
    server = FakeUKServer().start()
    try:
        settings = Settings(
            uk_base_url=f"http://127.0.0.1:{server.port}",
            uk_username="admin",
            uk_password="pw",
            uk_connect_timeout=5.0,
            uk_reconnect_delay_max=1.0,
            bridge_allow_anonymous=True,
        )
        runtime = BridgeRuntime(settings)
        await runtime.start()
        try:
            await _wait_until(lambda: runtime.state is RuntimeState.ready)
            await _wait_until(lambda: runtime.store.bootstrapped)

            async def heartbeat_ready() -> bool:
                heartbeat = await runtime.store.latest_heartbeat(1)
                return heartbeat is not None and heartbeat.ping == 42

            while not await heartbeat_ready():
                await asyncio.sleep(0.05)

            app = create_app(settings, runtime)
            app.state.runtime = runtime
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
                monitors = await client.get("/v1/monitors")
                assert monitors.status_code == 200
                item = monitors.json()["items"][0]
                assert item["id"] == 1
                assert item["status"] == "UP"
                assert item["ping"] == 42

                beats = await client.get("/v1/monitors/1/heartbeats")
                assert beats.json()["items"][0]["status"] == "UP"

                created = await client.post("/v1/monitors", json={"name": "New", "type": "http"})
                assert created.status_code == 201
                assert created.json()["data"]["monitor_id"] == 42
        finally:
            await runtime.stop()
    finally:
        server.stop()
