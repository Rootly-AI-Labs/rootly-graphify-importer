"""Run the graphify pipeline on an already-exported Rootly corpus.

Calls the existing Python pipeline functions directly so there is no
subprocess overhead and the integration stays type-safe.

The pipeline runs deterministically:
  extract (incidents + alerts + teams) → build → cluster → analyze → report → export

Node types: incident, alert, team, service
Edge types:
  triggered      alert     → incident   (alert caused incident)
  affects        incident  → service    (incident hit service)
  owns           team      → service    (team owns service)
  responded_by   incident  → team       (team responded to incident)
  targets        alert     → service    (orphan alert targets service)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from graphify.models_rootly import GraphifyMode


@dataclass
class RunResult:
    corpus_dir: Path
    graph_dir: Path          # graphify-out inside corpus_dir
    success: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Lightweight markdown extraction for the Rootly corpus
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Turn arbitrary text into a stable node ID."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:80]


def _read_field(text: str, field: str) -> str:
    """Extract a markdown field value: '- **Field:** value'."""
    m = re.search(rf"\*\*{re.escape(field)}:\*\*\s*(.+)", text)
    return m.group(1).strip() if m else ""


def _extract_markdown_corpus(corpus_dir: Path) -> dict:
    """Build a graphify extraction dict from Rootly incident, alert, and team files.

    Node types: incident, alert, team, service
    Edge types:
      triggered      alert     → incident
      affects        incident  → service
      owns           team      → service
      responded_by   incident  → team
      targets        alert     → service  (orphan alerts only)
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    inc_dir   = corpus_dir / "incidents"
    alert_dir = corpus_dir / "alerts"
    team_dir  = corpus_dir / "teams"

    # Maps for cross-referencing
    incident_nodes: dict[str, str] = {}  # rootly_incident_id  → graph node_id
    service_nodes:  dict[str, str] = {}  # service_name (lower) → graph node_id
    team_nodes:     dict[str, str] = {}  # team_name (lower)    → graph node_id

    def _get_or_create_service(name: str, source_file: str) -> str:
        key = name.lower().strip()
        if key in service_nodes:
            return service_nodes[key]
        node_id = _slug(f"service_{key}")
        service_nodes[key] = node_id
        if node_id not in seen_ids:
            seen_ids.add(node_id)
            nodes.append({
                "id": node_id,
                "label": f"Service: {name}",
                "node_type": "service",
                "file_type": "document",
                "source_file": source_file,
            })
        return node_id

    def _get_or_create_team(name: str, source_file: str) -> str:
        key = name.lower().strip()
        if key in team_nodes:
            return team_nodes[key]
        node_id = _slug(f"team_{key}")
        team_nodes[key] = node_id
        if node_id not in seen_ids:
            seen_ids.add(node_id)
            nodes.append({
                "id": node_id,
                "label": f"Team: {name}",
                "node_type": "team",
                "file_type": "document",
                "source_file": source_file,
            })
        return node_id

    # ------------------------------------------------------------------ #
    # 1. Incidents
    # ------------------------------------------------------------------ #
    if inc_dir.exists():
        for md_path in sorted(inc_dir.glob("incident_*.md")):
            text    = md_path.read_text(encoding="utf-8", errors="replace")
            src     = str(md_path.relative_to(corpus_dir))
            inc_id  = md_path.stem.replace("incident_", "")
            node_id = _slug(f"incident_{inc_id}")

            if node_id in seen_ids:
                incident_nodes[inc_id] = node_id
                continue
            seen_ids.add(node_id)
            incident_nodes[inc_id] = node_id

            title       = _read_field(text, "Title") or md_path.stem
            severity    = _read_field(text, "Severity")
            status      = _read_field(text, "Status")
            started_at  = _read_field(text, "Started At")
            ack_at      = _read_field(text, "Acknowledged At")
            mit_at      = _read_field(text, "Mitigated At")
            resolved_at = _read_field(text, "Resolved At")
            services_raw = _read_field(text, "Services")
            teams_raw    = _read_field(text, "Teams")

            nodes.append({
                "id": node_id,
                "label": f"Incident: {title}",
                "node_type": "incident",
                "file_type": "document",
                "source_file": src,
                # filter / colour metadata
                "severity":     severity,
                "status":       status,
                "started_at":   started_at,
                "acknowledged_at": ack_at,
                "mitigated_at": mit_at,
                "resolved_at":  resolved_at,
            })

            # incident → service edges
            if services_raw and services_raw != "N/A":
                for svc_name in [s.strip() for s in services_raw.split(",") if s.strip()]:
                    svc_node = _get_or_create_service(svc_name, src)
                    edges.append({
                        "source": node_id, "target": svc_node,
                        "relation": "affects",
                        "confidence": "EXTRACTED", "confidence_score": 1.0,
                        "source_file": src,
                    })

            # incident → team edges (responded_by)
            if teams_raw and teams_raw != "N/A":
                for team_name in [t.strip() for t in teams_raw.split(",") if t.strip()]:
                    team_node = _get_or_create_team(team_name, src)
                    edges.append({
                        "source": node_id, "target": team_node,
                        "relation": "responded_by",
                        "confidence": "EXTRACTED", "confidence_score": 1.0,
                        "source_file": src,
                    })

    # ------------------------------------------------------------------ #
    # 2. Teams — also read from teams/ dir for owns edges if present
    # ------------------------------------------------------------------ #
    if team_dir.exists():
        for md_path in sorted(team_dir.glob("team_*.md")):
            text      = md_path.read_text(encoding="utf-8", errors="replace")
            src       = str(md_path.relative_to(corpus_dir))
            team_name = _read_field(text, "Name") or md_path.stem
            _get_or_create_team(team_name, src)
            # owns edges are resolved later via alert service_ids cross-ref;
            # direct service ownership requires teams API data (in .json files)
            json_path = md_path.with_suffix(".json")
            if json_path.exists():
                try:
                    raw = json.loads(json_path.read_text(encoding="utf-8"))
                    # services may be embedded in relationships or attributes
                    attrs = raw.get("attributes", {})
                    svcs  = attrs.get("services") or []
                    team_node = team_nodes.get(team_name.lower().strip(), "")
                    for svc in svcs:
                        svc_name = svc.get("name", "") if isinstance(svc, dict) else str(svc)
                        if svc_name:
                            svc_node = _get_or_create_service(svc_name, src)
                            if team_node:
                                edges.append({
                                    "source": team_node, "target": svc_node,
                                    "relation": "owns",
                                    "confidence": "EXTRACTED", "confidence_score": 1.0,
                                    "source_file": src,
                                })
                except Exception:
                    pass

    # ------------------------------------------------------------------ #
    # 3. Alerts
    # ------------------------------------------------------------------ #
    incident_id_set = set(incident_nodes.keys())

    if alert_dir.exists():
        for md_path in sorted(alert_dir.glob("alert_*.md")):
            text      = md_path.read_text(encoding="utf-8", errors="replace")
            src       = str(md_path.relative_to(corpus_dir))
            alert_id  = md_path.stem.replace("alert_", "")
            node_id   = _slug(f"alert_{alert_id}")

            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            summary    = _read_field(text, "Summary") or md_path.stem
            status     = _read_field(text, "Status")
            source     = _read_field(text, "Source")
            noise      = _read_field(text, "Noise")
            started_at = _read_field(text, "Started At")
            ended_at   = _read_field(text, "Ended At")

            # Determine whether this alert triggered an incident
            inc_id_match = re.search(
                r"\*\*Incident ID:\*\*\s*([A-Za-z0-9\-]+)", text
            )
            linked_inc_id = ""
            if inc_id_match:
                candidate = inc_id_match.group(1).strip()
                if candidate.lower() not in ("none", "(none", ""):
                    linked_inc_id = candidate

            has_incident = bool(linked_inc_id and linked_inc_id in incident_id_set)

            nodes.append({
                "id": node_id,
                "label": f"Alert: {summary}",
                "node_type": "alert",
                "file_type": "document",
                "source_file": src,
                # filter / colour metadata
                "status":       status,
                "source_name":  source,
                "noise":        noise,
                "started_at":   started_at,
                "ended_at":     ended_at,
                "has_incident": has_incident,
                "incident_id":  linked_inc_id,
            })

            if has_incident:
                # alert → triggered → incident
                inc_node = incident_nodes.get(linked_inc_id, "")
                if inc_node:
                    edges.append({
                        "source": node_id, "target": inc_node,
                        "relation": "triggered",
                        "confidence": "EXTRACTED", "confidence_score": 1.0,
                        "source_file": src,
                    })
            else:
                # orphan alert → targets → service (from .json service_ids)
                json_path = md_path.with_suffix(".json")
                if json_path.exists():
                    try:
                        raw   = json.loads(json_path.read_text(encoding="utf-8"))
                        attrs = raw.get("attributes", {})
                        svc_ids = attrs.get("service_ids") or []
                        for sid in svc_ids:
                            # Try to match service_id to a known service by
                            # checking all service .json files
                            svc_name = _resolve_service_name(corpus_dir, str(sid))
                            if svc_name:
                                svc_node = _get_or_create_service(svc_name, src)
                                edges.append({
                                    "source": node_id, "target": svc_node,
                                    "relation": "targets",
                                    "confidence": "EXTRACTED", "confidence_score": 1.0,
                                    "source_file": src,
                                })
                    except Exception:
                        pass

    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _resolve_service_name(corpus_dir: Path, service_id: str) -> str:
    """Try to resolve a service ID to a name by scanning incident JSON files."""
    # Check incidents for matching service id in raw data
    inc_dir = corpus_dir / "incidents"
    if not inc_dir.exists():
        return ""
    for json_path in inc_dir.glob("incident_*.json"):
        try:
            raw   = json.loads(json_path.read_text(encoding="utf-8"))
            attrs = raw.get("attributes", {})
            svcs  = attrs.get("services") or []
            for svc in svcs:
                if isinstance(svc, dict) and str(svc.get("id", "")) == service_id:
                    return svc.get("name", "")
        except Exception:
            pass
    return ""


def _count_words(corpus_dir: Path) -> int:
    """Count total words across all markdown files in the corpus."""
    total = 0
    for md_path in corpus_dir.rglob("*.md"):
        try:
            total += len(md_path.read_text(encoding="utf-8", errors="replace").split())
        except OSError:
            pass
    return total


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

def run_graphify(corpus_dir: Path, mode: GraphifyMode) -> RunResult:
    """Run the graphify extraction pipeline on corpus_dir.

    Returns a RunResult; never raises — the caller can print a summary even
    on partial failure.
    """
    graph_dir = corpus_dir / "graphify-out"
    try:
        _run_pipeline(corpus_dir, mode, graph_dir)
        return RunResult(corpus_dir=corpus_dir, graph_dir=graph_dir, success=True)
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            corpus_dir=corpus_dir,
            graph_dir=graph_dir,
            success=False,
            error=str(exc),
        )


def _run_pipeline(corpus_dir: Path, mode: GraphifyMode, graph_dir: Path) -> None:
    """Inner pipeline – raises on error."""
    from graphify.build import build
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate as render_report
    from graphify.export import to_json, to_html

    flags = mode.extra_flags
    no_viz = "--no-viz" in flags

    graph_dir.mkdir(parents=True, exist_ok=True)

    # ---- extract nodes from markdown corpus ----
    print("  Extracting Rootly corpus…")
    extraction = _extract_markdown_corpus(corpus_dir)
    if not extraction["nodes"]:
        print("  Warning: no incident, alert, or team markdown files found.")

    # ---- build graph ----
    G = build([extraction])

    # ---- cluster ----
    print("  Clustering…")
    communities: dict[int, list[str]] = cluster(G)
    cohesion_scores = score_all(G, communities)

    # Auto-label communities (plain labels; Claude Code can enrich them)
    community_labels: dict[int, str] = {cid: f"Community {cid}" for cid in communities}

    # ---- analyze ----
    god_node_list = god_nodes(G)
    surprise_list = surprising_connections(G, communities)
    suggested_qs = suggest_questions(G, communities, community_labels)

    # Build a detection_result-compatible dict for the report
    md_count = len(list(corpus_dir.rglob("*.md")))
    detection_result = {
        "total_files": md_count,
        "total_words": _count_words(corpus_dir),
        "warning": None if md_count > 0 else "No markdown files found in corpus.",
        "needs_graph": md_count > 0,
    }
    token_cost = {"input": 0, "output": 0}

    # ---- report ----
    print("  Generating report…")
    report_text = render_report(
        G,
        communities,
        cohesion_scores,
        community_labels,
        god_node_list,
        surprise_list,
        detection_result,
        token_cost,
        str(corpus_dir),
        suggested_questions=suggested_qs,
    )
    (graph_dir / "GRAPH_REPORT.md").write_text(report_text, encoding="utf-8")

    # ---- export graph.json ----
    to_json(G, communities, str(graph_dir / "graph.json"))

    # ---- HTML visualization (unless --no-viz) ----
    if not no_viz:
        try:
            to_html(
                G, communities, str(graph_dir / "graph.html"),
                community_labels=community_labels,
                rootly=True,
            )
        except ValueError as exc:
            # Graph may exceed MAX_NODES_FOR_VIZ
            print(f"  Note: HTML visualization skipped – {exc}")

    # ---- optional exports ----
    if "--obsidian" in flags or "--wiki" in flags:
        try:
            from graphify.wiki import to_wiki
            to_wiki(G, communities, str(graph_dir / "wiki"), community_labels=community_labels)
        except Exception as exc:
            print(f"  Warning: wiki export failed: {exc}")

    if "--svg" in flags:
        try:
            from graphify.export import to_svg
            to_svg(G, communities, str(graph_dir / "graph.svg"), community_labels=community_labels)
        except Exception as exc:
            print(f"  Warning: SVG export failed: {exc}")

    if "--graphml" in flags:
        try:
            from graphify.export import to_graphml
            to_graphml(G, communities, str(graph_dir / "graph.graphml"))
        except Exception as exc:
            print(f"  Warning: GraphML export failed: {exc}")

    if "--neo4j" in flags:
        try:
            from graphify.export import to_cypher
            cypher_path = graph_dir / "cypher.txt"
            to_cypher(G, str(cypher_path))
            print(f"  Cypher exported → {cypher_path}")
        except Exception as exc:
            print(f"  Warning: Neo4j export failed: {exc}")
