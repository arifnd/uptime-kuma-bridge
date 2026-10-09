"""Bridge error hierarchy and HTTP mapping (task-012)."""

from __future__ import annotations

from typing import Any


class BridgeError(Exception):
    """Base class for all bridge errors.

    Subclasses define the stable ``code``, ``http_status`` and ``retriable``
    values that are surfaced to API clients.
    """

    code: str = "internal_error"
    http_status: int = 500
    retriable: bool = False

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail: dict[str, Any] = detail or {}


class NotFoundError(BridgeError):
    code = "not_found"
    http_status = 404


class MonitorNotFoundError(NotFoundError):
    code = "monitor_not_found"


class ValidationError(BridgeError):
    code = "validation_error"
    http_status = 422


class NotReadyError(BridgeError):
    code = "not_ready"
    http_status = 503
    retriable = True


class UpstreamUnavailable(BridgeError):
    code = "upstream_unavailable"
    http_status = 503
    retriable = True


class UpstreamTimeout(BridgeError):
    code = "upstream_timeout"
    http_status = 504
    retriable = True


class UpstreamError(BridgeError):
    code = "upstream_error"
    http_status = 502


class AuthError(BridgeError):
    code = "uk_auth_failed"
    http_status = 502
    retriable = True


class AuthFailed(AuthError):
    pass


class TwoFactorRequired(AuthFailed):
    code = "uk_twofactor_required"


class UKRejected(BridgeError):
    code = "uk_rejected"
    http_status = 400


class UKConflict(BridgeError):
    code = "uk_conflict"
    http_status = 409


class UnauthorizedError(BridgeError):
    code = "unauthorized"
    http_status = 401


class ForbiddenError(BridgeError):
    code = "forbidden"
    http_status = 403
