# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The public REST contract under `/v1` is additive-only within the major version.

## [0.1.0] - 2026-10-09

### Added

- Initial bridge implementation targeting Uptime Kuma >= 2.0.
- Persistent authenticated Socket.IO connection with reconnect + re-auth.
- In-memory state store for monitors, heartbeats, uptime, ping and cert info.
- Read REST API under `/v1` (monitors, status, heartbeats, uptime, ping, cert).
- Write REST API mapped to Socket.IO commands (add/edit/delete/pause/resume).
- SSE (`/v1/events`) and WebSocket (`/v1/ws`) streaming.
- API-key auth with read/write scopes, CORS allow-list, secret redaction.
- Prometheus metrics, health/readiness endpoints, optional upstream metrics proxy.
- Unit, component and end-to-end test suite.
