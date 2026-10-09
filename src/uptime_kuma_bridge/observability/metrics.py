"""Prometheus metrics (task-014)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

uk_connection_up = Gauge(
    "uk_connection_up", "1 when the bridge has an authenticated Socket.IO session"
)
uk_reconnect_total = Counter("uk_reconnect_total", "Number of reconnection attempts to Uptime Kuma")
uk_auth_failures_total = Counter(
    "uk_auth_failures_total",
    "Authentication failures against Uptime Kuma",
    ["reason"],
)
uk_events_total = Counter(
    "uk_events_total", "Socket.IO events received from Uptime Kuma", ["event"]
)
uk_event_parse_errors_total = Counter(
    "uk_event_parse_errors_total",
    "Events that failed to be parsed/normalized",
    ["event"],
)
uk_store_stale = Gauge(
    "uk_store_stale", "1 when the cached state is older than the staleness threshold"
)
bridge_http_requests_total = Counter(
    "bridge_http_requests_total",
    "HTTP requests served by the bridge",
    ["method", "route", "status"],
)
bridge_stream_subscribers = Gauge("bridge_stream_subscribers", "Active SSE/WebSocket subscribers")
bridge_command_duration_seconds = Histogram(
    "bridge_command_duration_seconds",
    "Duration of Socket.IO command round-trips",
    ["event"],
)


__all__ = [
    "bridge_command_duration_seconds",
    "bridge_http_requests_total",
    "bridge_stream_subscribers",
    "uk_auth_failures_total",
    "uk_connection_up",
    "uk_event_parse_errors_total",
    "uk_events_total",
    "uk_reconnect_total",
    "uk_store_stale",
]
