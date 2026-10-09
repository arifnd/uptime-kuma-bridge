"""Exception handlers enforcing the error contract (task-012)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..errors import BridgeError
from ..models.schemas import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _response(status_code: int, detail: ErrorDetail, request: Request) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    headers = {"X-Request-ID": request_id} if request_id else None
    body = ErrorResponse(error=detail).model_dump()
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BridgeError)
    async def _handle_bridge_error(request: Request, exc: BridgeError) -> JSONResponse:
        logger.warning("Bridge error: %s (%s)", exc.message, exc.code)
        return _response(
            exc.http_status,
            ErrorDetail(
                code=exc.code,
                message=exc.message,
                detail=exc.detail or None,
                retriable=exc.retriable,
            ),
            request,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _response(
            422,
            ErrorDetail(
                code="validation_error",
                message="Request validation failed",
                detail={"errors": jsonable_encoder(exc.errors())},
                retriable=False,
            ),
            request,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error while serving %s", request.url.path)
        return _response(
            500,
            ErrorDetail(
                code="internal_error",
                message="An internal error occurred",
                detail=None,
                retriable=False,
            ),
            request,
        )
