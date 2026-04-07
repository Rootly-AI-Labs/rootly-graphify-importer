"""Run the graphify pipeline on an already-exported Rootly corpus.

Calls the existing Python pipeline functions directly so there is no
subprocess overhead and the integration stays type-safe.

The pipeline runs deterministically:
  extract (markdown nodes) → build → cluster → analyze → report → export

For the Rootly corpus (all markdown files) a lightweight markdown extraction
step builds one node per incident/retrospective and links them by ID.

A tip is printed at the end encouraging `/graphify <dir>` in Claude Code
for richer LLM-powered semantic extraction on top.
"""
from __future__ import annotations

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


def _extract_markdown_corpus(corpus_dir: Path) -> dict:
    """Build a graphify extraction dict from Rootly markdown files.

    Produces:
    - One node per incident markdown (label = incident title)
    - One node per retrospective markdown (label = retrospective title)
    - An edge from each incident to its retrospective(s) when the
      retrospective body contains a matching Incident ID field.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    inc_dir = corpus_dir / "incidents"
    retro_dir = corpus_dir / "retrospectives"

    # --- incidents ---
    incident_nodes: dict[str, str] = {}   # rootly_incident_id → graph_node_id
    if inc_dir.exists():
        for md_path in sorted(inc_dir.glob("incident_*.md")):
            text = md_path.read_text(encoding="utf-8", errors="replace")
            title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_path.stem

            inc_id = md_path.stem.replace("incident_", "")
            node_id = _slug(f"incident_{inc_id}")
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            incident_nodes[inc_id] = node_id
            nodes.append({
                "id": node_id,
                "label": title,
                "source_file": str(md_path.relative_to(corpus_dir)),
                "file_type": "document",
            })

    # --- retrospectives ---
    if retro_dir.exists():
        for md_path in sorted(retro_dir.glob("retrospective_*.md")):
            text = md_path.read_text(encoding="utf-8", errors="replace")
            title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_path.stem

            retro_id = md_path.stem.replace("retrospective_", "")
            node_id = _slug(f"retrospective_{retro_id}")
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            nodes.append({
                "id": node_id,
                "label": title,
                "source_file": str(md_path.relative_to(corpus_dir)),
                "file_type": "document",
            })

            # Link retrospective → its incident when the Incident ID field is present
            inc_id_match = re.search(r"\*\*Incident ID:\*\*\s*([A-Za-z0-9\-]+)", text)
            if inc_id_match:
                linked_inc_id = inc_id_match.group(1).strip()
                inc_node_id = incident_nodes.get(linked_inc_id)
                if inc_node_id:
                    edges.append({
                        "source": inc_node_id,
                        "target": node_id,
                        "relation": "has_retrospective",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": str(md_path.relative_to(corpus_dir)),
                    })

    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


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
        print("  Warning: no incident or retrospective markdown files found.")

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
            to_html(G, communities, str(graph_dir / "graph.html"), community_labels=community_labels)
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
