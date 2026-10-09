"""Health, readiness and metrics endpoints (task-014)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..models.convert import server_info_to_dto
from ..models.schemas import ReadinessResponse, ServerInfoDTO
from ..runtime import BridgeRuntime
from ..uk.rest import fetch_upstream_metrics
from .deps import get_runtime, make_auth_dependency

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=ReadinessResponse)
async def readyz(runtime: Annotated[BridgeRuntime, Depends(get_runtime)]):
    return ReadinessResponse.model_validate(await runtime.readiness())


@router.get("/v1/info", response_model=ServerInfoDTO)
async def server_info(
    runtime: Annotated[BridgeRuntime, Depends(get_runtime)],
):
    return server_info_to_dto(await runtime.store.server_info())


@router.get("/metrics", dependencies=[Depends(make_auth_dependency("read"))])
async def metrics_endpoint() -> PlainTextResponse:
    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST.split(";")[0],
    )


@router.get(
    "/metrics/upstream",
    response_model=None,
    dependencies=[Depends(make_auth_dependency("read"))],
)
async def upstream_metrics(runtime: Annotated[BridgeRuntime, Depends(get_runtime)]):
    settings = runtime.settings
    content = await fetch_upstream_metrics(settings)
    return PlainTextResponse(
        content=content,
        media_type=CONTENT_TYPE_LATEST.split(";")[0],
    )
