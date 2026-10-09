"""Runtime lifecycle and reconnect tests (task-011)."""

from __future__ import annotations

import asyncio

from uptime_kuma_bridge.runtime import BridgeRuntime, RuntimeState


async def _wait_until(condition, timeout: float = 3.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met within timeout")


async def test_start_becomes_ready(runtime: BridgeRuntime) -> None:
    await runtime.start()
    try:
        await _wait_until(lambda: runtime.state is RuntimeState.ready)
        assert runtime.auth.method == "login"
        readiness = await runtime.readiness()
        assert readiness["status"] == "degraded"  # no snapshot yet
        await runtime.store.apply_monitor_list({"1": {"id": 1, "name": "A", "type": "http"}})
        assert (await runtime.readiness())["status"] == "ready"
    finally:
        await runtime.stop()
    assert runtime.state is RuntimeState.stopped


async def test_reconnect_after_disconnect(runtime: BridgeRuntime, fake_client) -> None:
    def login_count() -> int:
        return len([e for e in fake_client.emitted if e[0] == "login"])

    await runtime.start()
    try:
        await _wait_until(lambda: runtime.state is RuntimeState.ready)
        await fake_client.disconnect()
        await _wait_until(lambda: login_count() >= 2, timeout=5.0)
        await _wait_until(lambda: runtime.state is RuntimeState.ready, timeout=5.0)
        assert login_count() >= 2
    finally:
        await runtime.stop()


async def test_connection_error_enters_degraded(runtime: BridgeRuntime, fake_client) -> None:
    fake_client.connect_error = ConnectionRefusedError("boom")
    await runtime.start()
    try:
        await _wait_until(lambda: runtime.state is RuntimeState.degraded)
        fake_client.connect_error = None
    finally:
        await runtime.stop()
