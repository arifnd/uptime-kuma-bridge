"""An in-process fake Uptime Kuma Socket.IO server for end-to-end tests."""

from __future__ import annotations

import socket
import threading
import time

import socketio
import uvicorn


class FakeUKServer:
    def __init__(self, *, require_2fa: bool = False) -> None:
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.app = socketio.ASGIApp(self.sio)
        self.require_2fa = require_2fa
        self.monitors = {
            "1": {
                "id": 1,
                "name": "Site",
                "type": "http",
                "url": "https://example.com",
                "active": True,
            }
        }
        self.heartbeat = {
            "monitorID": 1,
            "status": 1,
            "msg": "OK",
            "ping": 42,
            "time": "2026-01-01T00:00:00Z",
            "important": True,
        }
        self.tokens = {"test-token"}
        self.port: int | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._register()

    def _register(self) -> None:
        sio = self.sio

        @sio.on("login")
        async def login(sid, data):
            if self.require_2fa and not (data or {}).get("token"):
                return {"ok": False, "tokenRequired": True, "msg": "2FA required"}
            await sio.emit("monitorList", self.monitors, to=sid)
            await sio.emit("info", {"version": "2.0.0", "serverTimezone": "UTC"}, to=sid)
            sio.start_background_task(self._delayed_heartbeat, sid)
            return {"ok": True, "token": "test-token"}

        @sio.on("loginByToken")
        async def login_by_token(sid, token):
            if token not in self.tokens:
                return {"ok": False, "msg": "invalid token"}
            await sio.emit("monitorList", self.monitors, to=sid)
            return {"ok": True}

        @sio.on("add")
        async def add(sid, monitor):
            return {"ok": True, "monitorID": 42}

        @sio.on("editMonitor")
        async def edit_monitor(sid, monitor):
            return {"ok": True}

        @sio.on("deleteMonitor")
        async def delete_monitor(sid, monitor_id):
            return {"ok": True}

        @sio.on("pauseMonitor")
        async def pause_monitor(sid, monitor_id):
            return {"ok": True}

        @sio.on("resumeMonitor")
        async def resume_monitor(sid, monitor_id):
            return {"ok": True}

        @sio.on("getMonitorBeats")
        async def get_beats(sid, monitor_id, period):
            return {"ok": True, "data": [self.heartbeat]}

    async def _delayed_heartbeat(self, sid) -> None:
        await self.sio.sleep(0.1)
        await self.sio.emit("heartbeat", self.heartbeat, to=sid)

    def start(self) -> FakeUKServer:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        config = uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="error")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 10
        while not self._server.started and time.time() < deadline:
            time.sleep(0.05)
        if not self._server.started:
            raise RuntimeError("fake Uptime Kuma server did not start")
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
