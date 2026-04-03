from __future__ import annotations
from datetime import date
import networkx as nx


def generate(
    G: nx.Graph,
    communities: dict[int, list[str]],
    cohesion_scores: dict[int, float],
    community_labels: dict[int, str],
    god_node_list: list[dict],
    surprise_list: list[dict],
    detection_result: dict,
    token_cost: dict,
    root: str,
) -> str:
    today = date.today().isoformat()

    confidences = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
    total = len(confidences) or 1
    ext_pct = round(confidences.count("EXTRACTED") / total * 100)
    inf_pct = round(confidences.count("INFERRED") / total * 100)
    amb_pct = round(confidences.count("AMBIGUOUS") / total * 100)

    lines = [
        f"# Graph Report — {root}  ({today})",
        "",
        "## Corpus Check",
    ]
    if detection_result.get("warning"):
        lines.append(f"- {detection_result['warning']}")
    else:
        lines += [
            f"- {detection_result['total_files']} files · ~{detection_result['total_words']:,} words",
            "- Verdict: corpus is large enough that graph structure adds value.",
        ]

    lines += [
        "",
        "## Summary",
        f"- {G.number_of_nodes()} nodes · {G.number_of_edges()} edges · {len(communities)} communities detected",
        f"- Extraction: {ext_pct}% EXTRACTED · {inf_pct}% INFERRED · {amb_pct}% AMBIGUOUS",
        f"- Token cost: {token_cost.get('input', 0):,} input · {token_cost.get('output', 0):,} output",
        "",
        "## God Nodes (most connected — your core abstractions)",
    ]
    for i, node in enumerate(god_node_list, 1):
        lines.append(f"{i}. `{node['label']}` — {node['edges']} edges")

    lines += ["", "## Surprising Connections (you probably didn't know these)"]
    if surprise_list:
        for s in surprise_list:
            lines += [
                f"- `{s['source']}` ↔ `{s['target']}`  [{s['confidence']}]",
                f"  {s['source_files'][0]} ↔ {s['source_files'][1]}",
            ]
    else:
        lines.append("- None detected — all connections are within the same source files.")

    lines += ["", "## Communities"]
    for cid, nodes in communities.items():
        label = community_labels.get(cid, f"Community {cid}")
        score = cohesion_scores.get(cid, 0.0)
        node_labels = [G.nodes[n].get("label", n) for n in nodes[:8]]
        suffix = "..." if len(nodes) > 8 else ""
        lines += [
            "",
            f"### Community {cid} — \"{label}\"",
            f"Cohesion: {score}",
            f"Nodes ({len(nodes)}): {', '.join(node_labels)}{suffix}",
        ]

    ambiguous = [(u, v, d) for u, v, d in G.edges(data=True) if d.get("confidence") == "AMBIGUOUS"]
    if ambiguous:
        lines += ["", "## Ambiguous Edges — Review These"]
        for u, v, d in ambiguous:
            ul = G.nodes[u].get("label", u)
            vl = G.nodes[v].get("label", v)
            lines += [
                f"- `{ul}` → `{vl}`  [AMBIGUOUS]",
                f"  {d.get('source_file', '')} · relation: {d.get('relation', 'unknown')}",
            ]

    return "\n".join(lines)
