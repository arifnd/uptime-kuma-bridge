"""State store tests (task-005)."""

from __future__ import annotations

import asyncio

import pytest

from uptime_kuma_bridge.store.state import StateStore


async def test_monitor_list_and_reads() -> None:
    store = StateStore()
    await store.apply_monitor_list(
        {"1": {"id": 1, "name": "A", "type": "http"}, "2": {"name": "B", "type": "tcp"}}
    )
    monitors = await store.list_monitors()
    assert {m.id for m in monitors} == {1, 2}
    assert store.bootstrapped is True
    assert (await store.get_monitor(1)).name == "A"  # type: ignore[union-attr]


async def test_reads_return_copies() -> None:
    store = StateStore()
    await store.apply_monitor_list({"1": {"id": 1, "name": "A", "type": "http"}})
    monitor = await store.get_monitor(1)
    assert monitor is not None
    monitor.name = "mutated"
    assert (await store.get_monitor(1)).name == "A"  # type: ignore[union-attr]


async def test_heartbeat_buffer_is_bounded() -> None:
    store = StateStore(heartbeat_buffer=3)
    await store.apply_monitor_list({"1": {"id": 1, "name": "A", "type": "http"}})
    for i in range(5):
        await store.apply_heartbeat({"monitorID": 1, "status": 1, "ping": i})
    beats = await store.heartbeats(1)
    assert [b.ping for b in beats] == [2.0, 3.0, 4.0]
    assert (await store.latest_heartbeat(1)).ping == 4.0  # type: ignore[union-attr]


async def test_delete_removes_all_data() -> None:
    store = StateStore()
    await store.apply_monitor_list({"1": {"id": 1, "name": "A", "type": "http"}})
    await store.apply_heartbeat({"monitorID": 1, "status": 1})
    await store.apply_uptime(1, "24", 0.9)
    await store.apply_monitor_delete(1)
    assert await store.get_monitor(1) is None
    assert await store.heartbeats(1) == []
    assert await store.uptime(1) == {}


async def test_uptime_ping_cert_info() -> None:
    store = StateStore()
    await store.apply_uptime(1, "24", 0.95)
    await store.apply_avg_ping(1, 12.0)
    await store.apply_cert_info(1, {"subject": {"CN": "x"}, "valid_to": "2999-01-01T00:00:00Z"})
    assert (await store.uptime(1))["24"] == 0.95
    assert await store.avg_ping(1) == 12.0
    assert (await store.cert_info(1)).valid is True  # type: ignore[union-attr]


async def test_staleness() -> None:
    store = StateStore(stale_after=0.05)
    assert store.is_stale() is True
    await store.apply_info({"version": "2.0.0"})
    assert store.is_stale() is False
    await asyncio.sleep(0.06)
    assert store.is_stale() is True


async def test_missing_monitor_returns_none() -> None:
    store = StateStore()
    assert await store.get_monitor(99) is None
    assert await store.latest_heartbeat(99) is None
    assert await store.cert_info(99) is None


@pytest.mark.parametrize("heartbeat", [{"status": 1}, {"monitorID": None, "status": 1}])
async def test_heartbeat_without_monitor_id_is_ignored(heartbeat: dict) -> None:
    store = StateStore()
    await store.apply_heartbeat(heartbeat)
    assert store.last_event_age() is None
