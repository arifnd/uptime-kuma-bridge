"""Socket.IO client foundation (task-003)."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

import socketio

from ..config import Settings
from ..errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


class ClientState(StrEnum):
    disconnected = "disconnected"
    connecting = "connecting"
    authenticating = "authenticating"
    ready = "ready"
    degraded = "degraded"


def _safe_set_result(future: asyncio.Future[Any], value: Any) -> None:
    if not future.done():
        future.set_result(value)


class UKSocketClient:
    """Thin wrapper around ``python-socketio``'s asyncio client.

    Owns the long-lived connection to Uptime Kuma, dispatches server-sent
    events to registered handlers, and provides an acknowledgement helper for
    command events.
    """

    def __init__(
        self,
        settings: Settings,
        sio: socketio.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._sio = (
            sio
            if sio is not None
            else socketio.AsyncClient(
                reconnection=False,
                ssl_verify=settings.uk_verify_tls,
            )
        )
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._state = ClientState.disconnected
        self._connected_event = asyncio.Event()
        self._disconnected_event = asyncio.Event()
        self._disconnected_event.set()
        self._register_internal_handlers()

    # --- event registration --------------------------------------------

    def _register_internal_handlers(self) -> None:
        self._sio.on("connect", self._on_connect)
        self._sio.on("disconnect", self._on_disconnect)
        self._sio.on("connect_error", self._on_connect_error)
        self._sio.on("*", self._on_unknown)

    def on(self, event: str, handler: Handler) -> None:
        """Register a handler for a server-sent event."""
        already = bool(self._handlers[event])
        self._handlers[event].append(handler)
        if not already:
            self._sio.on(event, self._make_dispatcher(event))

    def _make_dispatcher(self, event: str) -> Handler:
        async def dispatcher(*args: Any, **kwargs: Any) -> None:
            for handler in list(self._handlers.get(event, [])):
                try:
                    await handler(*args, **kwargs)
                except Exception:  # noqa: BLE001 - isolation between handlers
                    logger.exception("Handler for event %s failed", event)

        return dispatcher

    async def _on_connect(self, *_args: Any, **_kwargs: Any) -> None:
        self._connected_event.set()
        self._disconnected_event.clear()
        self._set_state(ClientState.connecting)
        logger.info("Connected to Uptime Kuma transport")

    async def _on_disconnect(self, *args: Any, **_kwargs: Any) -> None:
        self._connected_event.clear()
        self._disconnected_event.set()
        self._set_state(ClientState.degraded)
        logger.warning("Disconnected from Uptime Kuma: %s", args[0] if args else "unknown")

    async def _on_connect_error(self, data: Any = None) -> None:
        self._connected_event.clear()
        self._disconnected_event.set()
        logger.warning("Uptime Kuma connect_error: %s", data)

    async def _on_unknown(self, *args: Any) -> None:
        if args and isinstance(args[0], str):
            event = args[0]
            if event in self._handlers:
                return
            logger.debug("Unhandled Uptime Kuma event: %s", event)
        else:
            logger.debug("Unhandled transport payload: %r", args)

    # --- lifecycle ------------------------------------------------------

    async def connect(self) -> None:
        self._set_state(ClientState.connecting)
        await self._sio.connect(
            self.settings.socketio_url,
            socketio_path=self.settings.socketio_path,
            wait_timeout=self.settings.uk_connect_timeout,
        )

    async def disconnect(self) -> None:
        try:
            if getattr(self._sio, "connected", False):
                await self._sio.disconnect()
        except Exception:  # noqa: BLE001 - best-effort shutdown
            logger.debug("Error while disconnecting", exc_info=True)
        finally:
            self._set_state(ClientState.disconnected)
            self._connected_event.clear()
            self._disconnected_event.set()

    async def wait_connected(self, timeout: float | None = None) -> None:
        await asyncio.wait_for(self._connected_event.wait(), timeout)

    async def wait_disconnected(self) -> None:
        await self._disconnected_event.wait()

    # --- commands -------------------------------------------------------

    async def emit_ack(self, event: str, *args: Any, timeout: float = 10.0) -> Any:
        """Emit ``event`` and wait for the server acknowledgement callback."""
        if not self.connected:
            raise UpstreamUnavailable(f"Not connected to Uptime Kuma (event={event})")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        def ack(*ack_args: Any) -> None:
            if len(ack_args) > 1:
                result: Any = list(ack_args)
            elif ack_args:
                result = ack_args[0]
            else:
                result = None
            loop.call_soon_threadsafe(_safe_set_result, future, result)

        data: Any
        if len(args) == 1:
            data = args[0]
        elif args:
            data = tuple(args)
        else:
            data = None

        try:
            await self._sio.emit(event, data=data, callback=ack)
        except Exception as exc:  # noqa: BLE001 - normalize transport errors
            raise UpstreamError(f"Failed to emit {event}: {exc}") from exc

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            raise UpstreamTimeout(f"Timed out waiting for ack of {event}") from exc

    # --- state ----------------------------------------------------------

    def _set_state(self, state: ClientState) -> None:
        if state is not self._state:
            logger.info("Socket.IO state: %s -> %s", self._state.value, state.value)
            self._state = state

    @property
    def state(self) -> ClientState:
        return self._state

    @property
    def connected(self) -> bool:
        return bool(getattr(self._sio, "connected", False))

    @property
    def sio(self) -> socketio.AsyncClient:
        return self._sio
