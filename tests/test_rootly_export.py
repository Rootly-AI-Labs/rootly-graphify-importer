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
    RootlyRetrospective,
)
from graphify.rootly_export import (
    incident_to_markdown,
    retrospective_to_markdown,
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
        resolved_at="2026-04-01T12:30:00Z",
        description="Payments API latency exceeded SLO.",
        services=["Payments API"],
        teams=["SRE"],
        raw={"id": id},
    )


def _retro(id="retro-abc", incident_id="101") -> RootlyRetrospective:
    return RootlyRetrospective(
        id=id,
        incident_id=incident_id,
        incident_title="API latency spike",
        status="published",
        content="Root cause was a misconfigured load balancer.",
        created_at="2026-04-02T09:00:00Z",
        updated_at="2026-04-02T10:00:00Z",
        started_at="2026-04-01T11:00:00Z",
        mitigated_at="2026-04-01T12:00:00Z",
        resolved_at="2026-04-01T12:30:00Z",
        url="https://app.rootly.com/post_mortems/retro-abc",
        raw={"id": id},
    )


# ---------------------------------------------------------------------------
# Markdown formatting
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


def test_retrospective_markdown_contains_content(tmp_path):
    config = _config(tmp_path)
    md = retrospective_to_markdown(_retro(), config)
    assert "Root cause was a misconfigured load balancer" in md


def test_retrospective_markdown_contains_incident_id(tmp_path):
    config = _config(tmp_path)
    md = retrospective_to_markdown(_retro(incident_id="101"), config)
    assert "101" in md


def test_retrospective_markdown_contains_preset(tmp_path):
    config = _config(tmp_path)
    md = retrospective_to_markdown(_retro(), config)
    assert "past_30d" in md


def test_retrospective_markdown_no_api_key(tmp_path):
    """API key must never appear in any exported markdown."""
    config = _config(tmp_path)
    md = retrospective_to_markdown(_retro(), config)
    assert config.api_key not in md


def test_incident_markdown_no_api_key():
    incident = _incident()
    md = incident_to_markdown(incident)
    assert "rl_test_key" not in md


# ---------------------------------------------------------------------------
# Corpus directory structure
# ---------------------------------------------------------------------------

def test_export_creates_directory_structure(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    incidents = [_incident("101"), _incident("102", "DB failure")]
    retros = [_retro("r1", "101"), _retro("r2", "102")]

    corpus = export_rootly_corpus(output_dir, incidents, retros, config)

    assert corpus == output_dir
    assert (output_dir / "incidents" / "incident_101.md").exists()
    assert (output_dir / "incidents" / "incident_102.md").exists()
    assert (output_dir / "retrospectives" / "retrospective_r1.md").exists()
    assert (output_dir / "retrospectives" / "retrospective_r2.md").exists()
    assert (output_dir / "rootly-export.json").exists()
    assert (output_dir / "metadata" / "fetch_manifest.json").exists()
    assert (output_dir / "metadata" / "run_config.json").exists()


def test_export_raw_json_preserved(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    incidents = [_incident("55")]
    export_rootly_corpus(output_dir, incidents, [], config)

    raw_path = output_dir / "incidents" / "incident_55.json"
    assert raw_path.exists()
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    assert data["id"] == "55"


def test_export_manifest_counts(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    incidents = [_incident("1"), _incident("2")]
    retros = [_retro("r1", "1")]

    export_rootly_corpus(output_dir, incidents, retros, config)

    manifest = json.loads(
        (output_dir / "metadata" / "fetch_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["incident_count"] == 2
    assert manifest["retrospective_count"] == 1
    assert manifest["date_range_preset"] == "30d"


def test_export_run_config_no_api_key(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    export_rootly_corpus(output_dir, [], [], config)

    run_config = json.loads(
        (output_dir / "metadata" / "run_config.json").read_text(encoding="utf-8")
    )
    assert "api_key" not in run_config
    assert config.api_key not in json.dumps(run_config)


def test_export_combined_json(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    incidents = [_incident("11")]
    retros = [_retro("r9", "11")]
    export_rootly_corpus(output_dir, incidents, retros, config)

    combined = json.loads(
        (output_dir / "rootly-export.json").read_text(encoding="utf-8")
    )
    assert len(combined["incidents"]) == 1
    assert len(combined["retrospectives"]) == 1


def test_export_empty_corpus_creates_manifests(tmp_path):
    output_dir = tmp_path / "rootly-data"
    config = _config(output_dir)
    export_rootly_corpus(output_dir, [], [], config)

    assert (output_dir / "metadata" / "fetch_manifest.json").exists()
    manifest = json.loads(
        (output_dir / "metadata" / "fetch_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["incident_count"] == 0
    assert manifest["retrospective_count"] == 0
