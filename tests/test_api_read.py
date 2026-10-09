"""Read endpoint tests (task-008)."""

from __future__ import annotations

from .conftest import seed_monitor


async def test_list_monitors(runtime, api_client) -> None:
    await seed_monitor(runtime, 1)
    response = await api_client.get("/v1/monitors")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["id"] == 1
    assert item["status"] == "UP"
    assert item["ping"] == 42.0
    assert item["uptime_24h"] == 0.99


async def test_get_monitor_and_raw(runtime, api_client) -> None:
    await seed_monitor(runtime, 1)
    response = await api_client.get("/v1/monitors/1")
    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "https://example.com"
    assert body["accepted_statuscodes"] == []
    assert body["raw"] is None

    response = await api_client.get("/v1/monitors/1", params={"include": "raw"})
    assert response.json()["raw"]["id"] == 1


async def test_get_monitor_not_found(runtime, api_client) -> None:
    response = await api_client.get("/v1/monitors/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "monitor_not_found"


async def test_heartbeats_from_store(runtime, api_client) -> None:
    await seed_monitor(runtime, 1)
    response = await api_client.get("/v1/monitors/1/heartbeats")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["status"] == "UP"


async def test_heartbeats_live_fallback(runtime, api_client, fake_client) -> None:
    await runtime.store.apply_monitor_list({"1": {"id": 1, "name": "A", "type": "http"}})
    runtime.state = type(runtime.state).ready
    fake_client.acks["getMonitorBeats"] = {
        "ok": True,
        "data": [{"status": 0, "msg": "Down", "ping": None}],
    }
    response = await api_client.get("/v1/monitors/1/heartbeats")
    assert response.status_code == 200
    assert response.json()["items"][0]["status"] == "DOWN"


async def test_uptime_ping_cert_status(runtime, api_client) -> None:
    await seed_monitor(runtime, 1)
    uptime = await api_client.get("/v1/monitors/1/uptime", params={"period": "24h"})
    assert uptime.json()["percentage"] == 0.99

    ping = await api_client.get("/v1/monitors/1/ping")
    assert ping.json() == {"monitor_id": 1, "current": 42.0, "average": 50.0}

    cert = await api_client.get("/v1/monitors/1/cert")
    assert cert.status_code == 200
    assert cert.json()["monitor_id"] == 1

    status = await api_client.get("/v1/status")
    assert status.json()["items"][0]["status"] == "UP"


async def test_stale_flag(runtime, api_client) -> None:
    await seed_monitor(runtime, 1)
    runtime.store.stale_after = -1.0
    response = await api_client.get("/v1/monitors")
    assert response.json()["items"][0]["stale"] is True


async def test_list_monitors_empty(runtime, api_client) -> None:
    response = await api_client.get("/v1/monitors")
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}
