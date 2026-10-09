"""Upstream REST proxy and SSE generator tests (tasks-010, 014)."""

from __future__ import annotations

import asyncio

import httpx2
import pytest
from starlette.requests import Request

from uptime_kuma_bridge.api.routes_stream import stream_events
from uptime_kuma_bridge.errors import UpstreamError, UpstreamTimeout
from uptime_kuma_bridge.uk import rest

from .conftest import make_settings, seed_monitor


async def _never_receive():
    await asyncio.Event().wait()


async def test_sse_generator_emits_heartbeat(runtime) -> None:
    await seed_monitor(runtime, 1)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/events",
            "headers": [],
            "query_string": b"",
        },
        receive=_never_receive,
    )
    response = await stream_events(request, runtime, monitor=[1], event=None)
    assert response.media_type == "text/event-stream"
    iterator = response.body_iterator

    first = await iterator.__anext__()
    assert first.startswith(": connected")
    await runtime.bus.publish("heartbeat", {"monitor_id": 1, "status": 1})
    chunk = await asyncio.wait_for(iterator.__anext__(), timeout=2)
    assert "event: heartbeat" in chunk
    assert '"monitor_id": 1' in chunk
    await iterator.aclose()


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _FakeHTTPClient:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, auth=None):
        return _FakeResponse("uk_metric 1\n")


async def test_fetch_upstream_metrics(monkeypatch) -> None:
    monkeypatch.setattr(rest.httpx2, "AsyncClient", _FakeHTTPClient)
    content = await rest.fetch_upstream_metrics(make_settings())
    assert content == "uk_metric 1\n"


async def test_fetch_upstream_metrics_timeout(monkeypatch) -> None:
    class _TimeoutClient(_FakeHTTPClient):
        async def get(self, url, auth=None):
            raise httpx2.TimeoutException("slow")

    monkeypatch.setattr(rest.httpx2, "AsyncClient", _TimeoutClient)
    with pytest.raises(UpstreamTimeout):
        await rest.fetch_upstream_metrics(make_settings())


async def test_fetch_upstream_metrics_http_error(monkeypatch) -> None:
    class _ErrorClient(_FakeHTTPClient):
        async def get(self, url, auth=None):
            raise httpx2.ConnectError("nope")

    monkeypatch.setattr(rest.httpx2, "AsyncClient", _ErrorClient)
    with pytest.raises(UpstreamError):
        await rest.fetch_upstream_metrics(make_settings())
