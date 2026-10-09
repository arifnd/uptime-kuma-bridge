"""Real-time streaming API: SSE and WebSocket (task-010)."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ..errors import UnauthorizedError
from ..observability import metrics
from ..runtime import BridgeRuntime
from .deps import authorize_websocket, get_runtime, make_auth_dependency

router = APIRouter(
    prefix="/v1",
    tags=["stream"],
    dependencies=[Depends(make_auth_dependency("read"))],
)


@router.get("/events")
async def stream_events(
    request: Request,
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
    monitor: Annotated[list[int] | None, Query()] = None,
    event: Annotated[list[str] | None, Query()] = None,
):
    subscription = runtime.bus.subscribe(
        monitor_ids=set(monitor) if monitor else None,
        events=set(event) if event else None,
    )
    metrics.bridge_stream_subscribers.set(runtime.bus.subscriber_count)

    async def event_generator():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(subscription.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                payload = json.dumps(item.data, default=str)
                yield f"id: {item.seq}\nevent: {item.event}\ndata: {payload}\n\n"
        finally:
            runtime.bus.unsubscribe(subscription)
            metrics.bridge_stream_subscribers.set(runtime.bus.subscriber_count)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket):
    try:
        authorize_websocket(websocket, "read")
    except UnauthorizedError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    runtime: BridgeRuntime = websocket.app.state.runtime
    subscription = runtime.bus.subscribe()
    metrics.bridge_stream_subscribers.set(runtime.bus.subscriber_count)

    async def pump() -> None:
        while True:
            item = await subscription.get()
            await websocket.send_json({"id": item.seq, "event": item.event, "data": item.data})

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            if action == "subscribe":
                subscription.monitor_ids = (
                    set(message["monitor"]) if message.get("monitor") else None
                )
                subscription.events = set(message["event"]) if message.get("event") else None
            elif action == "unsubscribe":
                subscription.monitor_ids = None
                subscription.events = None
            elif action == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        await asyncio.gather(pump_task, return_exceptions=True)
        runtime.bus.unsubscribe(subscription)
        metrics.bridge_stream_subscribers.set(runtime.bus.subscriber_count)
