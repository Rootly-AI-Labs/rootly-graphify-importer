"""Tests for the rootly flow: models, mode mapping, runner extraction.

All tests are pure unit tests — no network, no questionary prompts,
no FS side effects outside tmp_path.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from graphify.models_rootly import GraphifyMode, RootlyFlowConfig


# ---------------------------------------------------------------------------
# GraphifyMode mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected_flags", [
    ("standard",    []),
    ("deep",        ["--mode", "deep"]),
    ("update",      ["--update"]),
    ("cluster_only", ["--cluster-only"]),
    ("no_viz",      ["--no-viz"]),
    ("obsidian",    ["--obsidian"]),
])
def test_mode_from_name_flags(name, expected_flags):
    mode = GraphifyMode.from_name(name)  # type: ignore[arg-type]
    assert mode.name == name
    assert mode.extra_flags == expected_flags


def test_mode_unknown_name_raises():
    with pytest.raises(KeyError):
        GraphifyMode.from_name("nonexistent")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RootlyFlowConfig
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path, preset="30d") -> RootlyFlowConfig:
    return RootlyFlowConfig(
        api_key="rootly_test1234567890abcd",
        date_range_preset=preset,  # type: ignore[arg-type]
        start_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
        output_dir=tmp_path,
        graphify_mode=GraphifyMode.from_name("standard"),
    )


def test_masked_key_hides_middle(tmp_path):
    config = _make_config(tmp_path)
    masked = config.masked_key()
    assert "****" in masked
    # Full key must not appear
    assert config.api_key not in masked


def test_masked_key_shows_prefix(tmp_path):
    config = _make_config(tmp_path)
    masked = config.masked_key()
    assert masked.startswith("rootly_")


def test_masked_key_short_key():
    from graphify.models_rootly import RootlyFlowConfig, GraphifyMode
    config = RootlyFlowConfig(
        api_key="short",
        date_range_preset="7d",  # type: ignore[arg-type]
        start_at=datetime.now(timezone.utc),
        end_at=datetime.now(timezone.utc),
        output_dir=Path("."),
        graphify_mode=GraphifyMode.from_name("standard"),
    )
    assert config.masked_key() == "rootly_****"


# ---------------------------------------------------------------------------
# Runner: markdown extraction
# ---------------------------------------------------------------------------

def _write_corpus(tmp_path: Path) -> None:
    """Write a minimal valid Rootly corpus to tmp_path."""
    inc_dir = tmp_path / "incidents"
    inc_dir.mkdir()
    (inc_dir / "incident_101.md").write_text(
        "# Rootly Incident: 101\n\n"
        "- **Incident ID:** 101\n"
        "- **Title:** API latency spike\n"
        "- **Severity:** SEV-2\n"
        "- **Status:** resolved\n"
        "- **Started At:** 2026-04-01T11:00:00Z\n"
        "- **Services:** Payments API\n"
        "- **Teams:** SRE\n\n"
        "## Description\n\nLatency exceeded SLO.\n",
        encoding="utf-8",
    )

    alert_dir = tmp_path / "alerts"
    alert_dir.mkdir()
    (alert_dir / "alert_a1.md").write_text(
        "# Rootly Alert: a1\n\n"
        "- **Alert ID:** a1\n"
        "- **Summary:** CPU spike on web-01\n"
        "- **Status:** resolved\n"
        "- **Source:** datadog\n"
        "- **Noise:** not_noise\n"
        "- **Started At:** 2026-04-01T10:55:00Z\n"
        "- **Ended At:** 2026-04-01T11:10:00Z\n"
        "- **Incident ID:** 101\n\n"
        "## Metadata\n\n- Source: Rootly API\n",
        encoding="utf-8",
    )


def test_extract_markdown_corpus_nodes(tmp_path):
    from graphify.rootly_runner import _extract_markdown_corpus
    _write_corpus(tmp_path)
    extraction = _extract_markdown_corpus(tmp_path)

    node_ids = {n["id"] for n in extraction["nodes"]}
    assert any("incident" in nid for nid in node_ids)
    assert any("alert" in nid for nid in node_ids)


def test_extract_markdown_corpus_edge(tmp_path):
    from graphify.rootly_runner import _extract_markdown_corpus
    _write_corpus(tmp_path)
    extraction = _extract_markdown_corpus(tmp_path)

    # Alert linked to incident should produce a triggered edge
    relations = [e["relation"] for e in extraction["edges"]]
    assert "triggered" in relations


def test_extract_markdown_corpus_empty(tmp_path):
    from graphify.rootly_runner import _extract_markdown_corpus
    extraction = _extract_markdown_corpus(tmp_path)
    assert extraction["nodes"] == []
    assert extraction["edges"] == []


def test_extract_markdown_corpus_no_duplicate_nodes(tmp_path):
    from graphify.rootly_runner import _extract_markdown_corpus
    _write_corpus(tmp_path)
    # A file with the same content but different name gets a different node ID
    # (nodes are keyed by filename, not content), so we get 2 distinct nodes.
    # What we're really checking is that NO node_id appears twice.
    (tmp_path / "incidents" / "incident_101_copy.md").write_text(
        "# Rootly Incident: 101\n\n- **Incident ID:** 101\n",
        encoding="utf-8",
    )
    extraction = _extract_markdown_corpus(tmp_path)
    node_ids = [n["id"] for n in extraction["nodes"]]
    # All node IDs must be unique (no duplicate entries in the list)
    assert len(node_ids) == len(set(node_ids))


# ---------------------------------------------------------------------------
# CLI flag parsing (integration-light, no subprocess)
# ---------------------------------------------------------------------------

def test_run_rootly_command_help_exits(capsys):
    """--help should print usage text and return cleanly (no SystemExit)."""
    from graphify.__main__ import _run_rootly_command

    # _run_rootly_command returns for --help (does not sys.exit)
    _run_rootly_command(["--help"])
    captured = capsys.readouterr()
    assert "rootly" in captured.out.lower() or "Usage" in captured.out
