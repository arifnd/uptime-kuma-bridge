"""FastAPI application factory (task-001 / task-011)."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import register_exception_handlers
from .api.routes_health import router as health_router
from .api.routes_read import router as read_router
from .api.routes_stream import router as stream_router
from .api.routes_write import router as write_router
from .config import Settings, get_settings
from .observability import metrics
from .observability.logging import configure_logging
from .runtime import BridgeRuntime

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    runtime: BridgeRuntime | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.secret_values)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime or BridgeRuntime(settings)
        await app.state.runtime.start()
        try:
            yield
        finally:
            await app.state.runtime.stop()

    app = FastAPI(
        title="Uptime Kuma Bridge",
        version=__version__,
        description=(
            "REST API in front of Uptime Kuma 2.x. Mirrors the Uptime Kuma "
            "Socket.IO stream and exposes it over HTTP."
        ),
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        route = getattr(request.scope.get("route"), "path", request.url.path)
        metrics.bridge_http_requests_total.labels(
            method=request.method, route=route, status=str(response.status_code)
        ).inc()
        return response

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(read_router)
    app.include_router(write_router)
    app.include_router(stream_router)
    return app


def run() -> None:
    """Entry point used by the console script."""
    import uvicorn

    uvicorn.run(
        "uptime_kuma_bridge.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
