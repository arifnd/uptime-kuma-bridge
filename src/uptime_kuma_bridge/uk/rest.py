"""Optional pass-through of Uptime Kuma's REST surface via httpx2 (task-014)."""

from __future__ import annotations

import logging

import httpx2

from ..config import Settings
from ..errors import UpstreamError, UpstreamTimeout

logger = logging.getLogger(__name__)


async def fetch_upstream_metrics(settings: Settings, *, timeout: float = 10.0) -> str:
    """Fetch Uptime Kuma's Prometheus metrics.

    Authentication follows Uptime Kuma's rules: API key or basic auth is only
    attached when credentials are configured on the bridge.
    """
    url = f"{settings.socketio_url}/metrics"
    auth = None
    if settings.uk_username and settings.uk_password:
        auth = httpx2.BasicAuth(settings.uk_username, settings.uk_password.get_secret_value())
    try:
        async with httpx2.AsyncClient(timeout=timeout, verify=settings.uk_verify_tls) as client:
            response = await client.get(url, auth=auth)
            response.raise_for_status()
            return response.text
    except httpx2.TimeoutException as exc:
        raise UpstreamTimeout("Timed out fetching upstream metrics") from exc
    except httpx2.HTTPError as exc:
        raise UpstreamError(f"Failed to fetch upstream metrics: {exc}") from exc
