"""Application runtime: lifecycle, reconnect and readiness (task-011)."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from enum import StrEnum
from typing import Any

from .config import Settings
from .errors import AuthError
from .observability import metrics
from .store.state import StateStore
from .uk.auth import Authenticator
from .uk.client import UKSocketClient
from .uk.commands import CommandService
from .uk.events import EventBus, EventRouter

logger = logging.getLogger(__name__)


class RuntimeState(StrEnum):
    starting = "starting"
    connecting = "connecting"
    authenticating = "authenticating"
    ready = "ready"
    degraded = "degraded"
    stopped = "stopped"


class BridgeRuntime:
    """Owns all shared singletons and the reconnect loop."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: UKSocketClient | None = None,
        store: StateStore | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.settings = settings
        self.client = client if client is not None else UKSocketClient(settings)
        self.store = (
            store
            if store is not None
            else StateStore(
                heartbeat_buffer=settings.bridge_heartbeat_buffer,
                stale_after=settings.bridge_stale_after,
            )
        )
        self.bus = bus if bus is not None else EventBus()
        self.auth = Authenticator(settings, self.client)
        self.router = EventRouter(self.store, self.bus, self.client)
        self.commands = CommandService(settings, self.client)

        self.state = RuntimeState.starting
        self.started_at = time.time()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    # --- lifecycle ------------------------------------------------------

    async def start(self) -> None:
        self.router.register()
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="uk-runtime")

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await self.client.disconnect()
        self.state = RuntimeState.stopped

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stopping:
            try:
                self._set_state(RuntimeState.connecting)
                metrics.uk_connection_up.set(0)
                metrics.uk_reconnect_total.inc()
                await self.client.connect()
                metrics.uk_connection_up.set(1)
                self._set_state(RuntimeState.authenticating)
                await self.auth.authenticate()
                self._set_state(RuntimeState.ready)
                backoff = 1.0
                await self.client.wait_disconnected()
                self._set_state(RuntimeState.degraded)
            except asyncio.CancelledError:
                raise
            except AuthError as exc:
                metrics.uk_auth_failures_total.labels(reason=type(exc).__name__).inc()
                logger.error("Authentication to Uptime Kuma failed: %s", exc)
                self._set_state(RuntimeState.degraded)
            except Exception as exc:  # noqa: BLE001 - keep retrying
                logger.warning("Uptime Kuma connection error: %s", exc)
                self._set_state(RuntimeState.degraded)
            finally:
                metrics.uk_connection_up.set(0)
                metrics.uk_store_stale.set(1 if self.store.is_stale() else 0)

            if self._stopping:
                break
            delay = backoff * (0.5 + random.random())
            await asyncio.sleep(min(delay, self.settings.uk_reconnect_delay_max))
            backoff = min(backoff * 2, self.settings.uk_reconnect_delay_max)

    def _set_state(self, state: RuntimeState) -> None:
        if state is not self.state:
            logger.info("Bridge state: %s -> %s", self.state.value, state.value)
            self.state = state

    # --- readiness ------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self.state is RuntimeState.ready and self.store.bootstrapped

    async def readiness(self) -> dict[str, Any]:
        from . import __version__

        info = await self.store.server_info()
        return {
            "status": "ready" if self.ready else "degraded",
            "bridge_version": __version__,
            "uptime_s": round(time.time() - self.started_at, 3),
            "bootstrapped": self.store.bootstrapped,
            "last_event_age_s": self.store.last_event_age(),
            "uk_version": info.version if info else None,
        }
