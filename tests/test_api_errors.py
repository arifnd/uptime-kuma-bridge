"""Auth scopes, error contract and health tests (tasks-012, 013, 014)."""

from __future__ import annotations

import httpx2

from uptime_kuma_bridge.app import create_app
from uptime_kuma_bridge.runtime import BridgeRuntime

from .conftest import FakeUKClient, make_settings, seed_monitor


def _client(settings) -> tuple[BridgeRuntime, httpx2.AsyncClient]:
    runtime = BridgeRuntime(settings, client=FakeUKClient())  # type: ignore[arg-type]
    app = create_app(settings, runtime)
    app.state.runtime = runtime
    transport = httpx2.ASGITransport(app=app)
    return runtime, httpx2.AsyncClient(transport=transport, base_url="http://test")


def _secured_settings():
    return make_settings(
        bridge_api_keys="readkey:r,writekey:rw",
        bridge_allow_anonymous=False,
    )


async def test_missing_key_is_unauthorized() -> None:
    _, client = _client(_secured_settings())
    async with client:
        response = await client.get("/v1/monitors")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_wrong_key_is_unauthorized() -> None:
    _, client = _client(_secured_settings())
    async with client:
        response = await client.get("/v1/monitors", headers={"X-API-Key": "nope"})
    assert response.status_code == 401


async def test_read_key_cannot_write() -> None:
    runtime, client = _client(_secured_settings())
    await seed_monitor(runtime, 1)
    async with client:
        response = await client.post(
            "/v1/monitors",
            json={"name": "A", "type": "http"},
            headers={"Authorization": "Bearer readkey"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_bearer_read_key_allows_reads() -> None:
    runtime, client = _client(_secured_settings())
    await seed_monitor(runtime, 1)
    async with client:
        response = await client.get("/v1/monitors", headers={"Authorization": "Bearer readkey"})
    assert response.status_code == 200


async def test_error_envelope_and_request_id() -> None:
    runtime, client = _client(_secured_settings())
    async with client:
        response = await client.get("/v1/monitors/404", headers={"Authorization": "Bearer readkey"})
    assert response.status_code == 404
    body = response.json()["error"]
    assert set(body) == {"code", "message", "detail", "retriable"}
    assert body["retriable"] is False
    assert response.headers.get("X-Request-ID")


async def test_health_is_unauthenticated() -> None:
    _, client = _client(_secured_settings())
    async with client:
        health = await client.get("/healthz")
        ready = await client.get("/readyz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "degraded"


async def test_metrics_requires_auth() -> None:
    _, client = _client(_secured_settings())
    async with client:
        unauthorized = await client.get("/metrics")
        authorized = await client.get("/metrics", headers={"X-API-Key": "readkey"})
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert "uk_connection_up" in authorized.text
