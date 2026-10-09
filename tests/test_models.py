"""Model and converter tests (task-007)."""

from __future__ import annotations

from uptime_kuma_bridge.models.convert import (
    cert_to_dto,
    heartbeat_to_dto,
    monitor_to_detail,
    monitor_to_summary,
)
from uptime_kuma_bridge.models.uk import (
    Heartbeat,
    Monitor,
    MonitorStatus,
    parse_cert_info,
    status_from_code,
)


def test_monitor_parses_aliases_and_extras() -> None:
    monitor = Monitor.model_validate(
        {
            "id": 1,
            "name": "Site",
            "type": "http",
            "retryInterval": 30,
            "accepted_statuscodes_json": '["200-299"]',
            "customField": "kept",
        }
    )
    assert monitor.retry_interval == 30
    assert monitor.accepted_statuscodes() == ["200-299"]
    assert monitor.model_extra["customField"] == "kept"


def test_status_mapping() -> None:
    assert status_from_code(0) is MonitorStatus.down
    assert status_from_code(1) is MonitorStatus.up
    assert status_from_code(2) is MonitorStatus.pending
    assert status_from_code(3) is MonitorStatus.maintenance
    assert status_from_code(99) is MonitorStatus.unknown
    assert status_from_code(None) is MonitorStatus.unknown


def test_heartbeat_dto() -> None:
    hb = Heartbeat.model_validate(
        {"monitorID": 5, "status": 1, "msg": "OK", "ping": 12.5, "time": "t"}
    )
    dto = heartbeat_to_dto(hb, 5)
    assert dto.monitor_id == 5
    assert dto.status is MonitorStatus.up
    assert dto.ping == 12.5


def test_monitor_summary_and_detail() -> None:
    monitor = Monitor.model_validate({"id": 1, "name": "Site", "type": "http"})
    hb = Heartbeat.model_validate({"monitorID": 1, "status": 0, "ping": None})
    summary = monitor_to_summary(monitor, heartbeat=hb, uptime_24h=0.5, stale=False)
    assert summary.status is MonitorStatus.down
    assert summary.uptime_24h == 0.5
    detail = monitor_to_detail(monitor, heartbeat=hb, uptime_24h=0.5, stale=False, raw={"id": 1})
    assert detail.raw == {"id": 1}


def test_parse_cert_info_from_json_string() -> None:
    cert = parse_cert_info('{"subject": {"CN": "example.com"}, "valid_to": "2999-01-01T00:00:00Z"}')
    assert cert is not None
    assert cert.subject == {"CN": "example.com"}
    assert cert.valid is True
    assert cert.days_remaining is not None


def test_parse_cert_info_invalid() -> None:
    assert parse_cert_info("not-json") is None
    assert parse_cert_info(None) is None


def test_cert_to_dto_none() -> None:
    dto = cert_to_dto(1, None)
    assert dto.monitor_id == 1
    assert dto.valid is None
