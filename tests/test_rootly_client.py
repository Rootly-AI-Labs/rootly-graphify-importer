"""Tests for graphify.rootly_client.

All tests are pure unit tests — no network calls, no FS side-effects.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from graphify.rootly_client import (
    _build_headers,
    _normalise_incident,
    _normalise_retrospective,
    date_range_to_datetimes,
)
from graphify.models_rootly import RootlyIncident


# ---------------------------------------------------------------------------
# Auth headers
# ---------------------------------------------------------------------------

def test_build_headers_bearer_token():
    headers = _build_headers("my-secret-key")
    assert headers["Authorization"] == "Bearer my-secret-key"
    assert "application/vnd.api+json" in headers["Content-Type"]
    assert "application/vnd.api+json" in headers["Accept"]


def test_build_headers_does_not_mutate():
    """Calling _build_headers twice must return independent dicts."""
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

    # end should be close to now
    assert before <= end <= after

    # start should be approximately `days` before end
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
    # Should not crash; severity defaults to empty string
    assert isinstance(incident.severity, str)


# ---------------------------------------------------------------------------
# Retrospective normalisation
# ---------------------------------------------------------------------------

def _make_retro_raw(
    id="retro-1",
    incident_id="123",
    status="published",
    content="Root cause: disk full",
    created_at="2026-04-02T09:00:00Z",
    updated_at="2026-04-02T10:00:00Z",
    started_at="2026-04-01T10:00:00Z",
    mitigated_at="2026-04-01T11:30:00Z",
    resolved_at="2026-04-01T12:00:00Z",
    url="https://app.rootly.com/postmortems/retro-1",
):
    return {
        "id": id,
        "type": "post_mortems",
        "attributes": {
            "status": status,
            "content": content,
            "created_at": created_at,
            "updated_at": updated_at,
            "started_at": started_at,
            "mitigated_at": mitigated_at,
            "resolved_at": resolved_at,
            "url": url,
        },
        "relationships": {
            "incident": {"data": {"id": incident_id, "type": "incidents"}}
        },
    }


def test_normalise_retrospective_links_incident():
    incident = RootlyIncident(
        id="123", title="DB outage", severity="SEV-1", status="resolved",
        started_at="2026-04-01T10:00:00Z", resolved_at="2026-04-01T12:00:00Z",
        description="", services=[], teams=[], raw={},
    )
    lookup = {"123": incident}
    raw = _make_retro_raw(incident_id="123")
    retro = _normalise_retrospective(raw, lookup)

    assert retro.id == "retro-1"
    assert retro.incident_id == "123"
    assert retro.incident_title == "DB outage"
    assert retro.content == "Root cause: disk full"
    assert retro.status == "published"


def test_normalise_retrospective_unknown_incident():
    raw = _make_retro_raw(incident_id="999")
    retro = _normalise_retrospective(raw, {})
    # Should not crash; incident_title defaults to empty string
    assert retro.incident_id == "999"
    assert isinstance(retro.incident_title, str)


# ---------------------------------------------------------------------------
# Masked key helper
# ---------------------------------------------------------------------------

def test_masked_key_format():
    from graphify.models_rootly import RootlyFlowConfig, GraphifyMode
    from datetime import datetime, timezone

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
    # The 'rootly_' prefix should be visible
    assert masked.startswith("rootly_")
