from __future__ import annotations
import networkx as nx


def god_nodes(G: nx.Graph, top_n: int = 10) -> list[dict]:
    """Return the top_n most-connected nodes — the core abstractions."""
    degree = dict(G.degree())
    sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        {
            "id": node_id,
            "label": G.nodes[node_id].get("label", node_id),
            "edges": deg,
        }
        for node_id, deg in sorted_nodes
    ]


def surprising_connections(
    G: nx.Graph,
    communities: dict[int, list[str]] | None = None,
    top_n: int = 5,
) -> list[dict]:
    """
    Find connections that are genuinely surprising — not obvious from file structure.

    Strategy:
    - Multi-file corpora: cross-file edges between real entities (not concept nodes).
      Sorted AMBIGUOUS → INFERRED → EXTRACTED.
    - Single-file / single-source corpora: cross-community edges that bridge
      distant parts of the graph (betweenness centrality on edges).
      These reveal non-obvious structural couplings.

    Concept nodes (empty source_file, or injected semantic annotations) are excluded
    from surprising connections because they are intentional, not discovered.
    """
    # Identify unique source files (ignore empty/null source_file)
    source_files = {
        data.get("source_file", "")
        for _, data in G.nodes(data=True)
        if data.get("source_file", "")
    }
    is_multi_source = len(source_files) > 1

    if is_multi_source:
        return _cross_file_surprises(G, top_n)
    else:
        return _cross_community_surprises(G, communities or {}, top_n)


def _is_concept_node(G: nx.Graph, node_id: str) -> bool:
    """
    Return True if this node is a manually-injected semantic concept node
    rather than a real entity found in source code.

    Signals:
    - Empty source_file
    - source_file doesn't look like a real file path (no extension)
    """
    data = G.nodes[node_id]
    source = data.get("source_file", "")
    if not source:
        return True
    # Has no file extension → probably a concept label, not a real file
    if "." not in source.split("/")[-1]:
        return True
    return False


def _cross_file_surprises(G: nx.Graph, top_n: int) -> list[dict]:
    """
    Cross-file edges between real code/doc entities.
    Excludes concept nodes. Sorted AMBIGUOUS first.
    """
    surprises = []
    order = {"AMBIGUOUS": 0, "INFERRED": 1, "EXTRACTED": 2}

    for u, v, data in G.edges(data=True):
        # Skip if either endpoint is a concept node
        if _is_concept_node(G, u) or _is_concept_node(G, v):
            continue

        u_source = G.nodes[u].get("source_file", "")
        v_source = G.nodes[v].get("source_file", "")

        if u_source and v_source and u_source != v_source:
            surprises.append({
                "source": G.nodes[u].get("label", u),
                "target": G.nodes[v].get("label", v),
                "source_files": [u_source, v_source],
                "confidence": data.get("confidence", "EXTRACTED"),
                "relation": data.get("relation", ""),
            })

    surprises.sort(key=lambda x: order.get(x["confidence"], 3))
    return surprises[:top_n]


def _cross_community_surprises(
    G: nx.Graph,
    communities: dict[int, list[str]],
    top_n: int,
) -> list[dict]:
    """
    For single-source corpora: find edges that bridge different communities.
    These are surprising because Leiden grouped everything else tightly —
    these edges cut across the natural structure.

    Falls back to high-betweenness edges if no community info is provided.
    """
    if not communities:
        # No community info — use edge betweenness centrality
        if G.number_of_edges() == 0:
            return []
        betweenness = nx.edge_betweenness_centrality(G)
        top_edges = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:top_n]
        result = []
        for (u, v), score in top_edges:
            data = G.edges[u, v]
            result.append({
                "source": G.nodes[u].get("label", u),
                "target": G.nodes[v].get("label", v),
                "source_files": [
                    G.nodes[u].get("source_file", ""),
                    G.nodes[v].get("source_file", ""),
                ],
                "confidence": data.get("confidence", "EXTRACTED"),
                "relation": data.get("relation", ""),
                "note": f"Bridges graph structure (betweenness={score:.3f})",
            })
        return result

    # Build node → community map
    node_community = {n: cid for cid, nodes in communities.items() for n in nodes}

    surprises = []
    for u, v, data in G.edges(data=True):
        cid_u = node_community.get(u)
        cid_v = node_community.get(v)
        if cid_u is not None and cid_v is not None and cid_u != cid_v:
            # This edge crosses community boundaries — interesting
            confidence = data.get("confidence", "EXTRACTED")
            surprises.append({
                "source": G.nodes[u].get("label", u),
                "target": G.nodes[v].get("label", v),
                "source_files": [
                    G.nodes[u].get("source_file", ""),
                    G.nodes[v].get("source_file", ""),
                ],
                "confidence": confidence,
                "relation": data.get("relation", ""),
                "note": f"Bridges community {cid_u} → community {cid_v}",
            })

    # Sort: AMBIGUOUS first, then INFERRED, then EXTRACTED
    order = {"AMBIGUOUS": 0, "INFERRED": 1, "EXTRACTED": 2}
    surprises.sort(key=lambda x: order.get(x["confidence"], 3))
    return surprises[:top_n]
