"""Write endpoint tests (task-009)."""

from __future__ import annotations

from .conftest import seed_monitor


async def test_write_requires_ready(runtime, api_client) -> None:
    response = await api_client.post("/v1/monitors", json={"name": "A", "type": "http"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"


async def test_add_monitor(runtime, api_client, fake_client) -> None:
    await seed_monitor(runtime, 1)
    fake_client.acks["add"] = {"ok": True, "monitorID": 7}
    response = await api_client.post(
        "/v1/monitors", json={"name": "New", "type": "http", "url": "https://x"}
    )
    assert response.status_code == 201
    assert response.json()["data"]["monitor_id"] == 7
    assert fake_client.emitted[0][0] == "add"


async def test_edit_delete_pause_resume(runtime, api_client, fake_client) -> None:
    await seed_monitor(runtime, 1)
    assert (
        await api_client.put("/v1/monitors/1", json={"name": "R", "type": "http"})
    ).status_code == 200
    assert (await api_client.post("/v1/monitors/1/pause")).status_code == 200
    assert (await api_client.post("/v1/monitors/1/resume")).status_code == 200
    assert (await api_client.delete("/v1/monitors/1")).status_code == 200
    assert [e[0] for e in fake_client.emitted] == [
        "editMonitor",
        "pauseMonitor",
        "resumeMonitor",
        "deleteMonitor",
    ]


async def test_write_unknown_monitor(runtime, api_client) -> None:
    await seed_monitor(runtime, 1)
    response = await api_client.delete("/v1/monitors/999")
    assert response.status_code == 404


async def test_validation_error(runtime, api_client) -> None:
    await seed_monitor(runtime, 1)
    response = await api_client.post("/v1/monitors", json={"type": "http"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_upstream_rejection_surfaces(runtime, api_client, fake_client) -> None:
    await seed_monitor(runtime, 1)
    fake_client.acks["deleteMonitor"] = {"ok": False, "msg": "Cannot delete"}
    response = await api_client.delete("/v1/monitors/1")
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "uk_rejected"
    assert body["detail"]["uk_msg"] == "Cannot delete"
