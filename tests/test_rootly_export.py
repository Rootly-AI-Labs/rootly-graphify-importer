"""Tests for graphify.rootly_export.

Pure unit tests — no network, no side effects outside tmp_path.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from graphify.models_rootly import (
    GraphifyMode,
    RootlyFlowConfig,
    RootlyIncident,
    RootlyAlert,
    RootlyTeam,
)
from graphify.rootly_export import (
    incident_to_markdown,
    alert_to_markdown,
    team_to_markdown,
    export_rootly_corpus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _config(output_dir: Path) -> RootlyFlowConfig:
    return RootlyFlowConfig(
        api_key="rl_test_key",
        date_range_preset="30d",
        start_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
        output_dir=output_dir,
        graphify_mode=GraphifyMode.from_name("standard"),
    )


def _incident(id="101", title="API latency spike") -> RootlyIncident:
    return RootlyIncident(
        id=id,
        title=title,
        severity="SEV-2",
        status="resolved",
        started_at="2026-04-01T11:00:00Z",
        acknowledged_at="2026-04-01T11:05:00Z",
        mitigated_at="2026-04-01T12:00:00Z",
        resolved_at="2026-04-01T12:30:00Z",
        description="Payments API latency exceeded SLO.",
        services=["Payments API"],
        teams=["SRE"],
        raw={"id": id},
    )


def _alert(id="alert-1", incident_id="101") -> RootlyAlert:
    return RootlyAlert(
        id=id,
        summary="CPU spike on web-01",
        status="resolved",
        source="datadog",
        noise="not_noise",
        started_at="2026-04-01T10:55:00Z",
        ended_at="2026-04-01T11:10:00Z",
        service_ids=["svc-1"],
        team_ids=["grp-1"],
        incident_id=incident_id,
        raw={"id": id},
    )


def _team(id="team-1", name="SRE") -> RootlyTeam:
    return RootlyTeam(id=id, name=name, slug="sre", raw={"id": id})


# ---------------------------------------------------------------------------
# Markdown formatting — incidents
# ---------------------------------------------------------------------------

def test_incident_markdown_contains_title():
    md = incident_to_markdown(_incident())
    assert "API latency spike" in md
    assert "SEV-2" in md
    assert "resolved" in md


def test_incident_markdown_contains_services():
    md = incident_to_markdown(_incident())
    assert "Payments API" in md


def test_incident_markdown_contains_description():
    md = incident_to_markdown(_incident())
    assert "Payments API latency exceeded SLO" in md


def test_incident_markdown_no_api_key():
    md = incident_to_markdown(_incident())
    assert "rl_test_key" not in md


def test_incident_markdown_contains_timeline_fields():
    md = incident_to_markdown(_incident())
    assert "Acknowledged At" in md
    assert "Mitigated At" in md


# ---------------------------------------------------------------------------
# Markdown formatting — alerts
# ---------------------------------------------------------------------------

def test_alert_markdown_contains_summary():
    md = alert_to_markdown(_alert())
    assert "CPU spike on web-01" in md


def test_alert_markdown_contains_source():
    md = alert_to_markdown(_alert())
    assert "datadog" in md


def test_alert_markdown_contains_incident_id():
    md = alert_to_markdown(_alert(incident_id="101"))
    assert "101" in md


def test_alert_markdown_orphan_line():
    alert = _alert(incident_id="")
    alert.incident_id = ""
    md = alert_to_markdown(alert)
    assert "orphan" in md.lower() or "(none" in md.lower()


# ---------------------------------------------------------------------------
# Markdown formatting — teams
# ---------------------------------------------------------------------------

def test_team_markdown_contains_name():
    md = team_to_markdown(_team())
    assert "SRE" in md


def test_team_markdown_contains_slug():
    md = team_to_markdown(_team())
    assert "sre" in md


# ---------------------------------------------------------------------------
# Corpus directory structure
# ---------------------------------------------------------------------------

def test_export_creates_directory_structure(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    incidents = [_incident("101"), _incident("102", "DB failure")]
    alerts = [_alert("a1", "101"), _alert("a2", "102")]
    teams = [_team("t1", "SRE")]

    corpus = export_rootly_corpus(output_dir, incidents, alerts, teams, config)

    assert corpus == output_dir
    assert (output_dir / "incidents" / "incident_101.md").exists()
    assert (output_dir / "incidents" / "incident_102.md").exists()
    assert (output_dir / "alerts" / "alert_a1.md").exists()
    assert (output_dir / "alerts" / "alert_a2.md").exists()
    assert (output_dir / "teams" / "team_t1.md").exists()
    assert (output_dir / "rootly-export.json").exists()
    assert (output_dir / "metadata" / "fetch_manifest.json").exists()
    assert (output_dir / "metadata" / "run_config.json").exists()


def test_export_raw_json_preserved(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    export_rootly_corpus(output_dir, [_incident("55")], [], [], config)

    raw_path = output_dir / "incidents" / "incident_55.json"
    assert raw_path.exists()
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    assert data["id"] == "55"


def test_export_alert_json_preserved(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    export_rootly_corpus(output_dir, [], [_alert("a99")], [], config)

    raw_path = output_dir / "alerts" / "alert_a99.json"
    assert raw_path.exists()
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    assert data["id"] == "a99"


def test_export_manifest_counts(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    incidents = [_incident("1"), _incident("2")]
    alerts = [_alert("a1", "1")]
    teams = [_team("t1")]

    export_rootly_corpus(output_dir, incidents, alerts, teams, config)

    manifest = json.loads(
        (output_dir / "metadata" / "fetch_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["incident_count"] == 2
    assert manifest["alert_count"] == 1
    assert manifest["team_count"] == 1
    assert manifest["date_range_preset"] == "30d"


def test_export_run_config_no_api_key(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    export_rootly_corpus(output_dir, [], [], [], config)

    run_config = json.loads(
        (output_dir / "metadata" / "run_config.json").read_text(encoding="utf-8")
    )
    assert "api_key" not in run_config
    assert config.api_key not in json.dumps(run_config)


def test_export_combined_json(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    export_rootly_corpus(output_dir, [_incident("11")], [_alert("a1", "11")], [_team("t1")], config)

    combined = json.loads(
        (output_dir / "rootly-export.json").read_text(encoding="utf-8")
    )
    assert len(combined["incidents"]) == 1
    assert len(combined["alerts"]) == 1
    assert len(combined["teams"]) == 1


def test_export_empty_corpus_creates_manifests(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    export_rootly_corpus(output_dir, [], [], [], config)

    manifest = json.loads(
        (output_dir / "metadata" / "fetch_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["incident_count"] == 0
    assert manifest["alert_count"] == 0
    assert manifest["team_count"] == 0
