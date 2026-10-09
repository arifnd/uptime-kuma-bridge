# Uptime Kuma Bridge

A **REST API bridge** in front of [Uptime Kuma](https://github.com/louislam/uptime-kuma) 2.x.

Uptime Kuma publishes live data (monitors, heartbeats, uptime, ping, certificate
info) over **Socket.IO**, which many tools, dashboards and AI agents cannot
consume. This service keeps a persistent, authenticated Socket.IO connection to
Uptime Kuma, mirrors that state in memory, and serves it to consumers over a
plain, versioned **HTTP/REST API** — plus optional SSE/WebSocket streaming.

## Architecture

```
        REST clients                         Bridge                         Uptime Kuma 2.x
  ┌──────────────────────┐        ┌──────────────────────────┐        ┌────────────────────────┐
  │ curl / SDK / Grafana │  HTTP  │  FastAPI (REST + SSE/WS) │  WS    │  Socket.IO server      │
  │ dashboards / AI apps │ ─────► │  ├─ state store (cache)  │ ─────► │  login / loginByToken  │
  │                      │ ◄───── │  └─ Socket.IO async clnt │ ◄───── │  heartbeat/uptime/...  │
  └──────────────────────┘        └──────────────────────────┘        └────────────────────────┘
                                         │  (optional REST proxy)
                                         ▼  httpx2
                                   UK REST (/metrics, /status-page, /badge, /api/push)
```

## Requirements

- Python 3.12+
- Uptime Kuma **>= 2.0** (Socket.IO 4.x). Uptime Kuma 1.x is **not** supported.
- Network access from the bridge to the Uptime Kuma instance.

## Quickstart

```bash
# 1. Install
uv sync --extra dev          # or: pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
#   edit UK_BASE_URL and credentials

# 3. Run
uv run uptime-kuma-bridge    # or: python -m uptime_kuma_bridge
```

Then:

```bash
curl -s localhost:8000/readyz
curl -s localhost:8000/v1/monitors
curl -s localhost:8000/v1/monitors/1/heartbeats
curl -N localhost:8000/v1/events          # SSE stream
```

Interactive API docs: <http://localhost:8000/docs>.

## Configuration

All settings are environment variables (or `.env`). See `.env.example`.

| Variable                 | Required | Default                 | Purpose                                              |
| ------------------------ | -------- | ----------------------- | ---------------------------------------------------- |
| `UK_BASE_URL`            | yes      | `http://localhost:3001` | Uptime Kuma base URL                                 |
| `UK_USERNAME`            | yes*     | —                       | Login username                                       |
| `UK_PASSWORD`            | yes*     | —                       | Login password                                       |
| `UK_JWT_TOKEN`           | no       | —                       | Pre-issued remember-me token (skips password login)  |
| `UK_2FA_TOKEN`           | no       | —                       | 2FA token for non-interactive logins                 |
| `UK_TOKEN_FILE`          | no       | —                       | Persist a refreshed JWT to this file (mode 0600)     |
| `UK_CONNECT_TIMEOUT`     | no       | `10`                    | Socket connect timeout (seconds)                     |
| `UK_RECONNECT_DELAY_MAX` | no       | `30`                    | Max reconnect backoff (seconds)                      |
| `UK_VERIFY_TLS`          | no       | `true`                  | Verify TLS certificates                              |
| `UK_SOCKETIO_PATH`       | no       | `socket.io`             | Socket.IO path                                       |
| `BRIDGE_API_KEYS`        | no       | —                       | Keys for inbound auth: `key`, `key:r`, `key:rw`      |
| `BRIDGE_CORS_ORIGINS`    | no       | —                       | Comma-separated allowed CORS origins                 |
| `BRIDGE_ALLOW_ANONYMOUS` | no       | `true`                  | Allow unauthenticated access when no keys are set    |
| `BRIDGE_STALE_AFTER`     | no       | `30`                    | Seconds before cached data is flagged stale          |
| `BRIDGE_HEARTBEAT_BUFFER`| no       | `100`                   | Heartbeats retained per monitor                       |
| `LOG_LEVEL`              | no       | `INFO`                  | Log level                                             |

\* Required unless `UK_JWT_TOKEN` is provided.

> **Security:** when `BRIDGE_API_KEYS` is empty the bridge is **unauthenticated**.
> Set `BRIDGE_ALLOW_ANONYMOUS=false` to refuse to start without keys, or configure
> keys and protect the port.

## API reference

| Method   | Path                            | Description                                  |
| -------- | ------------------------------- | -------------------------------------------- |
| `GET`    | `/healthz`                      | Liveness (unauthenticated)                   |
| `GET`    | `/readyz`                       | Readiness / degraded status (unauthenticated)|
| `GET`    | `/metrics`                      | Bridge Prometheus metrics                    |
| `GET`    | `/metrics/upstream`             | Proxy of Uptime Kuma `/metrics`              |
| `GET`    | `/v1/info`                      | Uptime Kuma version / timezone               |
| `GET`    | `/v1/monitors`                  | All monitors with current status             |
| `GET`    | `/v1/monitors/{id}`             | Monitor detail (`?include=raw`)              |
| `GET`    | `/v1/monitors/{id}/heartbeats`  | Recent heartbeats (`?limit=`, `?period=`)    |
| `GET`    | `/v1/monitors/{id}/uptime`      | Uptime % (`?period=24h\|7d\|30d\|1y`)         |
| `GET`    | `/v1/monitors/{id}/ping`        | Current and 24h average ping                 |
| `GET`    | `/v1/monitors/{id}/cert`        | TLS certificate info                         |
| `GET`    | `/v1/status`                    | Aggregate status list for dashboards         |
| `POST`   | `/v1/monitors`                  | Create a monitor                             |
| `PUT`    | `/v1/monitors/{id}`             | Update a monitor                             |
| `DELETE` | `/v1/monitors/{id}`             | Delete a monitor                             |
| `POST`   | `/v1/monitors/{id}/pause`       | Pause a monitor                              |
| `POST`   | `/v1/monitors/{id}/resume`      | Resume a monitor                             |
| `GET`    | `/v1/events`                    | Server-Sent Events stream                    |
| `WS`     | `/v1/ws`                        | WebSocket event stream                       |

Read endpoints require the `read` scope, write endpoints the `write` scope.
Errors use a stable envelope:

```json
{
  "error": {
    "code": "monitor_not_found",
    "message": "Monitor 42 was not found",
    "detail": null,
    "retriable": false
  }
}
```

## Deployment

```bash
docker compose up --build
```

> **Run a single worker.** The state store and event bus are in-memory, so the
> bridge is designed to run as one process. Do not scale replicas behind a load
> balancer, and do not start multiple Uvicorn workers.

Behind a reverse proxy, SSE requires buffering to be disabled, e.g. nginx:

```nginx
location /v1/events {
    proxy_buffering off;
    proxy_read_timeout 24h;
    proxy_set_header Connection "";
}
```

## Compatibility & caveats

- Targets Uptime Kuma **>= 2.0**. Tested against the 2.x Socket.IO protocol.
- Uptime Kuma's Socket.IO API is **internal and unsupported**; its payload shapes
  may change between releases. The bridge tolerates unknown fields and unknown
  events, and reports drift via logs and `uk_event_parse_errors_total`.
- Historical data is bounded and in-memory; restarts re-bootstrap from Uptime Kuma.

## Development

```bash
make install     # uv sync --extra dev
make check       # ruff + mypy + pytest
make openapi     # regenerate docs/openapi.json
```

Tests run offline (unit + component, backed by a fake Socket.IO client). One
end-to-end test starts a real in-process Socket.IO server. See
`tasks/design.md` and `tasks/reference.md` for the full plan.

## License

MIT
