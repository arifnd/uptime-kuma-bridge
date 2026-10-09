"""Command service tests (task-009)."""

from __future__ import annotations

import pytest

from uptime_kuma_bridge.errors import UKConflict, UKRejected, UpstreamError
from uptime_kuma_bridge.uk.commands import CommandService

from .conftest import FakeUKClient, make_settings


def make_service(acks: dict | None = None) -> tuple[CommandService, FakeUKClient]:
    client = FakeUKClient()
    if acks:
        client.acks.update(acks)
    service = CommandService(make_settings(), client)  # type: ignore[arg-type]
    return service, client


async def test_add_monitor_returns_id() -> None:
    service, client = make_service({"add": {"ok": True, "monitorID": 7}})
    monitor_id = await service.add_monitor({"name": "A", "type": "http"})
    assert monitor_id == 7
    assert client.emitted[0][0] == "add"


async def test_edit_delete_pause_resume() -> None:
    service, client = make_service()
    await service.edit_monitor({"id": 1, "name": "A"})
    await service.delete_monitor(1)
    await service.pause_monitor(1)
    await service.resume_monitor(1)
    assert [e[0] for e in client.emitted] == [
        "editMonitor",
        "deleteMonitor",
        "pauseMonitor",
        "resumeMonitor",
    ]


async def test_get_monitor_beats() -> None:
    service, _ = make_service({"getMonitorBeats": {"ok": True, "data": [{"status": 1}]}})
    beats = await service.get_monitor_beats(1, 24)
    assert beats == [{"status": 1}]


async def test_rejection_maps_to_uk_rejected() -> None:
    service, _ = make_service({"add": {"ok": False, "msg": "Bad monitor"}})
    with pytest.raises(UKRejected):
        await service.add_monitor({"name": "A"})


async def test_conflict_maps_to_uk_conflict() -> None:
    service, _ = make_service({"add": {"ok": False, "msg": "Monitor already exists"}})
    with pytest.raises(UKConflict):
        await service.add_monitor({"name": "A"})


async def test_non_dict_response_is_upstream_error() -> None:
    service, _ = make_service({"add": "weird"})
    with pytest.raises(UpstreamError):
        await service.add_monitor({"name": "A"})
