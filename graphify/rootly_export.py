"""Convert Rootly API objects into a graphify-ready local corpus.

Output layout:
    <output_dir>/
        rootly-export.json          raw combined JSON dump
        incidents/
            incident_<id>.md
        retrospectives/
            retrospective_<id>.md
        metadata/
            run_config.json
            fetch_manifest.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from graphify.models_rootly import (
    FetchManifest,
    GraphifyMode,
    RootlyFlowConfig,
    RootlyIncident,
    RootlyRetrospective,
)


# ---------------------------------------------------------------------------
# Markdown formatters
# ---------------------------------------------------------------------------

def _yaml_str(s: str) -> str:
    """Escape a string for embedding in a YAML double-quoted scalar."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def incident_to_markdown(incident: RootlyIncident) -> str:
    services = ", ".join(incident.services) if incident.services else "N/A"
    teams = ", ".join(incident.teams) if incident.teams else "N/A"
    description = incident.description.strip() if incident.description else "_No description provided._"

    return f"""\
# Rootly Incident: {incident.id}

- **Incident ID:** {incident.id}
- **Title:** {incident.title}
- **Severity:** {incident.severity or "N/A"}
- **Status:** {incident.status}
- **Started At:** {incident.started_at or "N/A"}
- **Resolved At:** {incident.resolved_at or "N/A"}
- **Services:** {services}
- **Teams:** {teams}

## Description

{description}

## Metadata

- Source: Rootly API
- Exported By: Graphify Rootly Flow
"""


def retrospective_to_markdown(
    retro: RootlyRetrospective,
    config: RootlyFlowConfig,
) -> str:
    content = retro.content.strip() if retro.content else "_No retrospective content recorded._"
    url_line = f"- **URL:** {retro.url}" if retro.url else ""

    return f"""\
# Rootly Retrospective: Incident {retro.incident_id}

- **Retrospective ID:** {retro.id}
- **Incident ID:** {retro.incident_id}
- **Title:** {retro.incident_title}
- **Status:** {retro.status}
- **Created At:** {retro.created_at or "N/A"}
- **Updated At:** {retro.updated_at or "N/A"}
- **Started At:** {retro.started_at or "N/A"}
- **Mitigated At:** {retro.mitigated_at or "N/A"}
- **Resolved At:** {retro.resolved_at or "N/A"}
{url_line}

## Retrospective Content

{content}

## Metadata

- Source: Rootly API
- Exported By: Graphify Rootly Flow
- Date Range Preset: past_{config.date_range_preset}
"""


# ---------------------------------------------------------------------------
# Directory writer
# ---------------------------------------------------------------------------

def _ensure_gitignore(output_dir: Path) -> None:
    """Add output_dir to the nearest .gitignore if we're inside a git repo."""
    # Walk up looking for a .gitignore in a git root
    candidate = output_dir.resolve()
    for parent in [candidate] + list(candidate.parents):
        git_dir = parent / ".git"
        if git_dir.exists():
            gitignore = parent / ".gitignore"
            dir_name = output_dir.resolve().name + "/"
            if gitignore.exists():
                existing = gitignore.read_text(encoding="utf-8")
                if dir_name in existing or output_dir.name + "/" in existing:
                    return
                gitignore.write_text(
                    existing.rstrip() + f"\n\n# Rootly exported corpus (may contain sensitive data)\n{dir_name}\n",
                    encoding="utf-8",
                )
            else:
                gitignore.write_text(
                    f"# Rootly exported corpus (may contain sensitive data)\n{dir_name}\n",
                    encoding="utf-8",
                )
            print(f"  .gitignore       →  added {dir_name}")
            return  # Only update the first (closest) .gitignore found


def write_manifest(
    output_dir: Path,
    config: RootlyFlowConfig,
    incidents: list[RootlyIncident],
    retrospectives: list[RootlyRetrospective],
) -> Path:
    manifest = FetchManifest(
        date_range_preset=config.date_range_preset,
        start_at=config.start_at.isoformat(),
        end_at=config.end_at.isoformat(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        incident_count=len(incidents),
        retrospective_count=len(retrospectives),
        graphify_mode=config.graphify_mode.name,
        output_dir=str(output_dir.resolve()),
    )

    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = metadata_dir / "fetch_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.__dict__, indent=2), encoding="utf-8"
    )
    return manifest_path


def write_run_config(output_dir: Path, config: RootlyFlowConfig) -> Path:
    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    run_config = {
        "date_range_preset": config.date_range_preset,
        "start_at": config.start_at.isoformat(),
        "end_at": config.end_at.isoformat(),
        "graphify_mode": config.graphify_mode.name,
        "extra_flags": config.graphify_mode.extra_flags,
        "output_dir": str(output_dir.resolve()),
        # api_key intentionally omitted
    }
    path = metadata_dir / "run_config.json"
    path.write_text(json.dumps(run_config, indent=2), encoding="utf-8")
    return path


def export_rootly_corpus(
    output_dir: Path,
    incidents: list[RootlyIncident],
    retrospectives: list[RootlyRetrospective],
    config: RootlyFlowConfig,
) -> Path:
    """Write the full Rootly corpus to disk. Returns the corpus directory.

    The directory is safe to pass directly to the graphify pipeline.
    Raw JSON is preserved alongside markdown for future richer extractors.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_gitignore(output_dir)

    # ---- incidents ----
    inc_dir = output_dir / "incidents"
    inc_dir.mkdir(exist_ok=True)
    for incident in incidents:
        md_path = inc_dir / f"incident_{incident.id}.md"
        md_path.write_text(incident_to_markdown(incident), encoding="utf-8")
        raw_path = inc_dir / f"incident_{incident.id}.json"
        raw_path.write_text(json.dumps(incident.raw, indent=2), encoding="utf-8")

    # ---- retrospectives ----
    retro_dir = output_dir / "retrospectives"
    retro_dir.mkdir(exist_ok=True)
    for retro in retrospectives:
        md_path = retro_dir / f"retrospective_{retro.id}.md"
        md_path.write_text(retrospective_to_markdown(retro, config), encoding="utf-8")
        raw_path = retro_dir / f"retrospective_{retro.id}.json"
        raw_path.write_text(json.dumps(retro.raw, indent=2), encoding="utf-8")

    # ---- combined raw dump ----
    combined = {
        "incidents": [i.raw for i in incidents],
        "retrospectives": [r.raw for r in retrospectives],
    }
    (output_dir / "rootly-export.json").write_text(
        json.dumps(combined, indent=2), encoding="utf-8"
    )

    # ---- metadata ----
    write_run_config(output_dir, config)
    write_manifest(output_dir, config, incidents, retrospectives)

    return output_dir
