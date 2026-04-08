"""Data models for the Rootly TUI flow.

Kept as plain dataclasses (no Pydantic dependency) to match the rest of
the graphify codebase which uses only stdlib types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


DateRangePreset = Literal["7d", "30d", "90d"]

GraphifyModeName = Literal[
    "standard", "deep", "update", "cluster_only", "no_viz", "obsidian"
]

AdvancedAction = Literal[
    "watch", "wiki", "svg", "graphml", "neo4j",
    "query", "path", "explain", "add_url",
]


@dataclass
class GraphifyMode:
    """Maps a human-readable mode label to the extra CLI flags it implies."""

    name: GraphifyModeName
    # Extra flags passed to the pipeline runner (e.g. ["--mode", "deep"])
    extra_flags: list[str] = field(default_factory=list)

    @staticmethod
    def from_name(name: GraphifyModeName) -> "GraphifyMode":
        _MAP: dict[str, list[str]] = {
            "standard":    [],
            "deep":        ["--mode", "deep"],
            "update":      ["--update"],
            "cluster_only": ["--cluster-only"],
            "no_viz":      ["--no-viz"],
            "obsidian":    ["--obsidian"],
        }
        return GraphifyMode(name=name, extra_flags=_MAP[name])


@dataclass
class RootlyFlowConfig:
    """Full configuration for a single Rootly TUI run."""

    api_key: str
    date_range_preset: DateRangePreset
    start_at: datetime
    end_at: datetime
    output_dir: Path
    graphify_mode: GraphifyMode
    advanced_action: AdvancedAction | None = None
    # True when key came from $ROOTLY_API_KEY env var
    use_env_key: bool = False

    def masked_key(self) -> str:
        """Return a safely masked version of the API key for logging.

        Rootly keys start with 'rootly_' so we show the prefix + last 4 chars:
        e.g. rootly_****a1b2
        """
        if len(self.api_key) <= 11:
            return "rootly_****"
        # Show up to the first 7 chars (the 'rootly_' prefix) + mask + last 4
        prefix = self.api_key[:7]
        return prefix + "****" + self.api_key[-4:]


@dataclass
class FetchManifest:
    """Written to disk after a successful fetch for traceability."""

    date_range_preset: DateRangePreset
    start_at: str          # ISO-8601
    end_at: str            # ISO-8601
    fetched_at: str        # ISO-8601
    incident_count: int
    retrospective_count: int
    graphify_mode: str
    output_dir: str


@dataclass
class RootlyIncident:
    """Normalised incident from the Rootly API."""

    id: str
    title: str
    severity: str
    status: str
    started_at: str
    acknowledged_at: str
    mitigated_at: str
    resolved_at: str
    description: str
    services: list[str]
    teams: list[str]
    # Raw JSON payload preserved for debugging / future richer extractors
    raw: dict


@dataclass
class RootlyAlert:
    """Normalised alert from the Rootly API."""

    id: str
    summary: str
    status: str          # open, triggered, acknowledged, resolved
    source: str          # datadog, pagerduty, rootly, etc.
    noise: str           # "noise", "not_noise", or ""
    started_at: str
    ended_at: str
    service_ids: list[str]
    team_ids: list[str]
    incident_id: str     # empty string if not attached to an incident
    raw: dict


@dataclass
class RootlyTeam:
    """Normalised team from the Rootly API."""

    id: str
    name: str
    slug: str
    raw: dict
