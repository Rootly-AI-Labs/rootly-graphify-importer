"""Convert Rootly API objects into a graphify-ready local corpus.

Output layout:
    <output_dir>/
        rootly-export.json          raw combined JSON dump
        incidents/
            incident_<id>.md
            incident_<id>.json
        alerts/
            alert_<id>.md
            alert_<id>.json
        teams/
            team_<id>.md
            team_<id>.json
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
    RootlyAlert,
    RootlyFlowConfig,
    RootlyIncident,
    RootlyTeam,
)


# ---------------------------------------------------------------------------
# Markdown formatters
# ---------------------------------------------------------------------------

def _yaml_str(s: str) -> str:
    """Escape a string for embedding in a YAML double-quoted scalar."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def incident_to_markdown(incident: RootlyIncident) -> str:
    services = ", ".join(incident.services) if incident.services else "N/A"
    teams    = ", ".join(incident.teams)    if incident.teams    else "N/A"
    description = incident.description.strip() if incident.description else "_No description provided._"

    return f"""\
# Rootly Incident: {incident.id}

- **Incident ID:** {incident.id}
- **Title:** {incident.title}
- **Severity:** {incident.severity or "N/A"}
- **Status:** {incident.status}
- **Started At:** {incident.started_at or "N/A"}
- **Acknowledged At:** {incident.acknowledged_at or "N/A"}
- **Mitigated At:** {incident.mitigated_at or "N/A"}
- **Resolved At:** {incident.resolved_at or "N/A"}
- **Services:** {services}
- **Teams:** {teams}

## Description

{description}

## Metadata

- Source: Rootly API
- Exported By: Graphify Rootly Flow
"""


def alert_to_markdown(alert: RootlyAlert) -> str:
    services = ", ".join(alert.service_ids) if alert.service_ids else "N/A"
    teams    = ", ".join(alert.team_ids)    if alert.team_ids    else "N/A"
    incident_line = f"- **Incident ID:** {alert.incident_id}" if alert.incident_id else "- **Incident ID:** (none — orphan alert)"

    return f"""\
# Rootly Alert: {alert.id}

- **Alert ID:** {alert.id}
- **Summary:** {alert.summary}
- **Status:** {alert.status}
- **Source:** {alert.source or "N/A"}
- **Noise:** {alert.noise or "N/A"}
- **Started At:** {alert.started_at or "N/A"}
- **Ended At:** {alert.ended_at or "N/A"}
- **Services:** {services}
- **Teams:** {teams}
{incident_line}

## Metadata

- Source: Rootly API
- Exported By: Graphify Rootly Flow
"""


def team_to_markdown(team: RootlyTeam) -> str:
    return f"""\
# Rootly Team: {team.id}

- **Team ID:** {team.id}
- **Name:** {team.name}
- **Slug:** {team.slug}

## Metadata

- Source: Rootly API
- Exported By: Graphify Rootly Flow
"""


# ---------------------------------------------------------------------------
# Directory writer
# ---------------------------------------------------------------------------

def _ensure_gitignore(output_dir: Path) -> None:
    """Add output_dir to the nearest .gitignore if we're inside a git repo."""
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
            return


def write_manifest(
    output_dir: Path,
    config: RootlyFlowConfig,
    incidents: list[RootlyIncident],
    alerts: list[RootlyAlert],
    teams: list[RootlyTeam],
) -> Path:
    manifest = FetchManifest(
        date_range_preset=config.date_range_preset,
        start_at=config.start_at.isoformat(),
        end_at=config.end_at.isoformat(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        incident_count=len(incidents),
        retrospective_count=0,
        graphify_mode=config.graphify_mode.name,
        output_dir=str(output_dir.resolve()),
    )

    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    # Extend manifest with alert + team counts
    manifest_dict = manifest.__dict__.copy()
    manifest_dict["alert_count"] = len(alerts)
    manifest_dict["team_count"]  = len(teams)

    manifest_path = metadata_dir / "fetch_manifest.json"
    manifest_path.write_text(json.dumps(manifest_dict, indent=2), encoding="utf-8")
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
    alerts: list[RootlyAlert],
    teams: list[RootlyTeam],
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
        (inc_dir / f"incident_{incident.id}.md").write_text(
            incident_to_markdown(incident), encoding="utf-8"
        )
        (inc_dir / f"incident_{incident.id}.json").write_text(
            json.dumps(incident.raw, indent=2), encoding="utf-8"
        )

    # ---- alerts ----
    alert_dir = output_dir / "alerts"
    alert_dir.mkdir(exist_ok=True)
    for alert in alerts:
        (alert_dir / f"alert_{alert.id}.md").write_text(
            alert_to_markdown(alert), encoding="utf-8"
        )
        (alert_dir / f"alert_{alert.id}.json").write_text(
            json.dumps(alert.raw, indent=2), encoding="utf-8"
        )

    # ---- teams ----
    team_dir = output_dir / "teams"
    team_dir.mkdir(exist_ok=True)
    for team in teams:
        (team_dir / f"team_{team.id}.md").write_text(
            team_to_markdown(team), encoding="utf-8"
        )
        (team_dir / f"team_{team.id}.json").write_text(
            json.dumps(team.raw, indent=2), encoding="utf-8"
        )

    # ---- combined raw dump ----
    combined = {
        "incidents": [i.raw for i in incidents],
        "alerts":    [a.raw for a in alerts],
        "teams":     [t.raw for t in teams],
    }
    (output_dir / "rootly-export.json").write_text(
        json.dumps(combined, indent=2), encoding="utf-8"
    )

    # ---- metadata ----
    write_run_config(output_dir, config)
    write_manifest(output_dir, config, incidents, alerts, teams)

    return output_dir
