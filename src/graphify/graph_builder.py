from __future__ import annotations
import networkx as nx


def build_from_json(extraction: dict) -> nx.Graph:
    G = nx.Graph()
    for node in extraction.get("nodes", []):
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in extraction.get("edges", []):
        G.add_edge(
            edge["source"],
            edge["target"],
            **{k: v for k, v in edge.items() if k not in ("source", "target")},
        )
    return G


def build(extractions: list[dict]) -> nx.Graph:
    """Merge multiple extraction results into one graph."""
    G = nx.Graph()
    for ext in extractions:
        sub = build_from_json(ext)
        G.update(sub)
    return G
