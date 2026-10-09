"""Event bus pub/sub tests (task-010 support)."""

from __future__ import annotations

from uptime_kuma_bridge.uk.events import EventBus


async def test_subscribe_and_receive() -> None:
    bus = EventBus()
    sub = bus.subscribe()
    await bus.publish("heartbeat", {"monitor_id": 1})
    event = await sub.get()
    assert event.event == "heartbeat"
    assert event.data["monitor_id"] == 1
    assert bus.subscriber_count == 1
    bus.unsubscribe(sub)
    assert bus.subscriber_count == 0


async def test_filters_by_event_and_monitor() -> None:
    bus = EventBus()
    sub = bus.subscribe(monitor_ids={1}, events={"heartbeat"})
    await bus.publish("heartbeat", {"monitor_id": 2})
    await bus.publish("uptime", {"monitor_id": 1})
    await bus.publish("heartbeat", {"monitor_id": 1})
    event = await sub.get()
    assert event.data["monitor_id"] == 1
    assert sub.queue.empty()


async def test_drop_oldest_on_overflow() -> None:
    bus = EventBus()
    sub = bus.subscribe()
    sub.queue = type(sub.queue)(maxsize=2)
    for i in range(5):
        await bus.publish("heartbeat", {"monitor_id": i})
    assert sub.dropped == 3
    assert sub.queue.qsize() == 2


async def test_monitor_list_matches_monitor_filter() -> None:
    bus = EventBus()
    sub = bus.subscribe(monitor_ids={1})
    await bus.publish("monitorList", {"monitor_ids": ["1", "2"]})
    assert not sub.queue.empty()
