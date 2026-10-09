# Tests

Layered test suite for the bridge.

| Layer          | Location                       | What it covers                                        |
| -------------- | ------------------------------ | ----------------------------------------------------- |
| Unit           | `test_config`, `test_models`, `test_store`, `test_eventbus`, `test_events`, `test_auth`, `test_commands` | Pure logic, parsers, store, auth, command mapping |
| Component      | `test_api_read`, `test_api_write`, `test_api_errors`, `test_runtime`, `test_stream` | FastAPI routes via an in-process fake client, error contract, auth scopes, runtime lifecycle |
| End-to-end     | `test_e2e`                     | A real `python-socketio` server (strategy: `fake_uk.FakeUKServer`) plus the real `UKSocketClient`, exercised through the REST app |

`conftest.py` provides `FakeUKClient`, settings and runtime fixtures and the
`api_client` (httpx2 `ASGITransport`) fixture.

## Running

```bash
make test                 # everything
pytest -m "not integration"   # skip the E2E test
pytest -m integration         # only the E2E test
```

`test_e2e` starts an in-process Socket.IO server on a random localhost port via
uvicorn; it needs no external services and no network access beyond loopback.

## Recording Uptime Kuma fixtures

Payloads in `test_events.py` are inline samples of Uptime Kuma 2.x events
(`monitorList`, `heartbeat`, `uptime`, `avgPing`, `certInfo`, `info`). They are
anonymous and contain no credentials. When Uptime Kuma's payloads change, update
the samples here and note the tested version.
