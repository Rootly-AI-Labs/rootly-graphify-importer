"""Tests for graphify.rootly_client.

All tests are pure unit tests — no network calls, no FS side-effects.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from graphify.rootly_client import (
    _build_headers,
    _normalise_incident,
    _normalise_alert,
    _normalise_team,
    date_range_to_datetimes,
)


# ---------------------------------------------------------------------------
# Auth headers
# ---------------------------------------------------------------------------

def test_build_headers_bearer_token():
    headers = _build_headers("my-secret-key")
    assert headers["Authorization"] == "Bearer my-secret-key"
    assert "application/vnd.api+json" in headers["Content-Type"]
    assert "application/vnd.api+json" in headers["Accept"]


def test_build_headers_does_not_mutate():
    h1 = _build_headers("key1")
    h2 = _build_headers("key2")
    assert h1["Authorization"] != h2["Authorization"]


# ---------------------------------------------------------------------------
# Date range presets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("preset,days", [("7d", 7), ("30d", 30), ("90d", 90)])
def test_date_range_to_datetimes_correct_window(preset, days):
    before = datetime.now(timezone.utc)
    start, end = date_range_to_datetimes(preset)  # type: ignore[arg-type]
    after = datetime.now(timezone.utc)

    assert before <= end <= after
    expected_delta = timedelta(days=days)
    actual_delta = end - start
    assert abs(actual_delta.total_seconds() - expected_delta.total_seconds()) < 5


def test_date_range_utc_aware():
    start, end = date_range_to_datetimes("30d")  # type: ignore[arg-type]
    assert start.tzinfo is not None
    assert end.tzinfo is not None


# ---------------------------------------------------------------------------
# Incident normalisation
# ---------------------------------------------------------------------------

def _make_incident_raw(
    id="123",
    title="Test Incident",
    status="resolved",
    started_at="2026-04-01T10:00:00Z",
    acknowledged_at="2026-04-01T10:05:00Z",
    mitigated_at="2026-04-01T11:00:00Z",
    resolved_at="2026-04-01T12:00:00Z",
    severity_name="SEV-2",
    summary="Something went wrong",
    services=None,
    teams=None,
):
    return {
        "id": id,
        "type": "incidents",
        "attributes": {
            "title": title,
            "status": status,
            "started_at": started_at,
            "acknowledged_at": acknowledged_at,
            "mitigated_at": mitigated_at,
            "resolved_at": resolved_at,
            "severity": {"name": severity_name},
            "summary": summary,
            "services": services or [],
            "teams": teams or [],
        },
    }


def test_normalise_incident_basic_fields():
    raw = _make_incident_raw(id="42", title="DB outage", severity_name="SEV-1")
    incident = _normalise_incident(raw)
    assert incident.id == "42"
    assert incident.title == "DB outage"
    assert incident.severity == "SEV-1"
    assert incident.status == "resolved"
    assert incident.started_at == "2026-04-01T10:00:00Z"
    assert incident.resolved_at == "2026-04-01T12:00:00Z"
    assert incident.description == "Something went wrong"


def test_normalise_incident_preserves_raw():
    raw = _make_incident_raw()
    incident = _normalise_incident(raw)
    assert incident.raw is raw


def test_normalise_incident_services_teams():
    raw = _make_incident_raw(
        services=[{"name": "Payments API"}, {"name": "Auth Service"}],
        teams=[{"name": "SRE"}],
    )
    incident = _normalise_incident(raw)
    assert "Payments API" in incident.services
    assert "Auth Service" in incident.services
    assert "SRE" in incident.teams


def test_normalise_incident_missing_severity():
    raw = _make_incident_raw()
    raw["attributes"]["severity"] = None
    incident = _normalise_incident(raw)
    assert isinstance(incident.severity, str)


def test_normalise_incident_acknowledged_mitigated():
    raw = _make_incident_raw(
        acknowledged_at="2026-04-01T10:05:00Z",
        mitigated_at="2026-04-01T11:30:00Z",
    )
    incident = _normalise_incident(raw)
    assert incident.acknowledged_at == "2026-04-01T10:05:00Z"
    assert incident.mitigated_at == "2026-04-01T11:30:00Z"


# ---------------------------------------------------------------------------
# Alert normalisation
# ---------------------------------------------------------------------------

def _make_alert_raw(
    id="alert-1",
    summary="CPU spike on web-01",
    status="resolved",
    source="datadog",
    noise="not_noise",
    started_at="2026-04-01T10:00:00Z",
    ended_at="2026-04-01T10:15:00Z",
    service_ids=None,
    group_ids=None,
    incidents=None,
):
    return {
        "id": id,
        "type": "alerts",
        "attributes": {
            "summary": summary,
            "status": status,
            "source": source,
            "noise": noise,
            "started_at": started_at,
            "ended_at": ended_at,
            "service_ids": service_ids or [],
            "group_ids": group_ids or [],
            "incidents": incidents or [],
        },
        "relationships": {},
    }


def test_normalise_alert_basic_fields():
    raw = _make_alert_raw()
    alert = _normalise_alert(raw)
    assert alert.id == "alert-1"
    assert alert.summary == "CPU spike on web-01"
    assert alert.status == "resolved"
    assert alert.source == "datadog"
    assert alert.noise == "not_noise"
    assert alert.started_at == "2026-04-01T10:00:00Z"
    assert alert.ended_at == "2026-04-01T10:15:00Z"


def test_normalise_alert_preserves_raw():
    raw = _make_alert_raw()
    alert = _normalise_alert(raw)
    assert alert.raw is raw


def test_normalise_alert_incident_id_from_incidents_array():
    """Primary path: incident_id read from attributes.incidents[0].id"""
    raw = _make_alert_raw(incidents=[{"id": "inc-42", "title": "DB outage"}])
    alert = _normalise_alert(raw)
    assert alert.incident_id == "inc-42"


def test_normalise_alert_incident_id_from_relationships():
    """Fallback: incident_id read from relationships.incident.data.id"""
    raw = _make_alert_raw()
    raw["relationships"]["incident"] = {"data": {"id": "inc-99", "type": "incidents"}}
    alert = _normalise_alert(raw)
    assert alert.incident_id == "inc-99"


def test_normalise_alert_no_incident_id():
    """Orphan alert: incident_id should be empty string."""
    raw = _make_alert_raw()
    alert = _normalise_alert(raw)
    assert alert.incident_id == ""


def test_normalise_alert_service_and_team_ids():
    raw = _make_alert_raw(service_ids=["svc-1", "svc-2"], group_ids=["grp-1"])
    alert = _normalise_alert(raw)
    assert alert.service_ids == ["svc-1", "svc-2"]
    assert alert.team_ids == ["grp-1"]


# ---------------------------------------------------------------------------
# Team normalisation
# ---------------------------------------------------------------------------

def _make_team_raw(id="team-1", name="SRE", slug="sre"):
    return {
        "id": id,
        "type": "teams",
        "attributes": {"name": name, "slug": slug},
    }


def test_normalise_team_basic_fields():
    raw = _make_team_raw()
    team = _normalise_team(raw)
    assert team.id == "team-1"
    assert team.name == "SRE"
    assert team.slug == "sre"


def test_normalise_team_preserves_raw():
    raw = _make_team_raw()
    team = _normalise_team(raw)
    assert team.raw is raw


# ---------------------------------------------------------------------------
# Masked key helper
# ---------------------------------------------------------------------------

def test_masked_key_format():
    from graphify.models_rootly import RootlyFlowConfig, GraphifyMode

    config = RootlyFlowConfig(
        api_key="rootly_abcdef1234567890",
        date_range_preset="30d",
        start_at=datetime.now(timezone.utc),
        end_at=datetime.now(timezone.utc),
        output_dir=__import__("pathlib").Path("."),
        graphify_mode=GraphifyMode.from_name("standard"),
    )
    masked = config.masked_key()
    assert "****" in masked
    assert config.api_key not in masked
    assert masked.startswith("rootly_")
