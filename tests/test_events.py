"""Event router ingestion tests (task-006)."""

from __future__ import annotations

from uptime_kuma_bridge.store.state import StateStore
from uptime_kuma_bridge.uk.events import EventBus, EventRouter

from .conftest import FakeUKClient


def make_router() -> tuple[EventRouter, StateStore, EventBus, FakeUKClient]:
    store = StateStore()
    bus = EventBus()
    client = FakeUKClient()
    router = EventRouter(store, bus, client)  # type: ignore[arg-type]
    router.register()
    return router, store, bus, client


async def test_monitor_list_and_info() -> None:
    _, store, _, client = make_router()
    await client.dispatch("monitorList", {"1": {"id": 1, "name": "A", "type": "http"}})
    await client.dispatch("info", {"version": "2.0.0", "serverTimezone": "UTC"})
    assert store.bootstrapped is True
    assert (await store.get_monitor(1)).name == "A"  # type: ignore[union-attr]
    assert (await store.server_info()).version == "2.0.0"  # type: ignore[union-attr]


async def test_heartbeat_uptime_ping_cert() -> None:
    _, store, bus, client = make_router()
    sub = bus.subscribe(events={"heartbeat", "uptime", "avgPing", "certInfo"})
    await client.dispatch("monitorList", {"1": {"id": 1, "name": "A", "type": "http"}})
    await client.dispatch("heartbeat", {"monitorID": 1, "status": 1, "ping": 5})
    await client.dispatch("uptime", 1, "24", 0.99)
    await client.dispatch("avgPing", 1, 12)
    await client.dispatch(
        "certInfo",
        1,
        '{"subject": {"CN": "x"}, "valid_to": "2999-01-01T00:00:00Z"}',
    )
    assert (await store.latest_heartbeat(1)).ping == 5  # type: ignore[union-attr]
    assert (await store.uptime(1))["24"] == 0.99
    assert await store.avg_ping(1) == 12
    assert (await store.cert_info(1)).valid is True  # type: ignore[union-attr]
    assert await sub.get()
    assert await sub.get()
    assert await sub.get()
    assert await sub.get()


async def test_update_and_delete_monitor() -> None:
    _, store, _, client = make_router()
    await client.dispatch("monitorList", {"1": {"id": 1, "name": "A", "type": "http"}})
    await client.dispatch("updateMonitorIntoList", {"1": {"id": 1, "name": "A2", "type": "http"}})
    assert (await store.get_monitor(1)).name == "A2"  # type: ignore[union-attr]
    await client.dispatch("deleteMonitorFromList", 1)
    assert await store.get_monitor(1) is None


async def test_malformed_event_is_isolated() -> None:
    _, store, _, client = make_router()
    await client.dispatch("heartbeat", "not-a-dict")
    # The failure is swallowed; the store remains usable.
    assert await store.latest_heartbeat(1) is None
