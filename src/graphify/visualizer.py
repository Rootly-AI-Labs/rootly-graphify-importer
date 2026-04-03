from __future__ import annotations
from pathlib import Path
import networkx as nx
from pyvis.network import Network

COMMUNITY_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]
MAX_NODES_FOR_VIZ = 5_000


def generate_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
) -> None:
    if G.number_of_nodes() > MAX_NODES_FOR_VIZ:
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes — too large for pyvis. "
            f"Use --no-viz or reduce input size."
        )

    node_community = {n: cid for cid, nodes in communities.items() for n in nodes}

    net = Network(height="800px", width="100%", bgcolor="#1a1a2e", font_color="white")
    net.barnes_hut()

    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        net.add_node(
            node_id,
            label=data.get("label", node_id),
            color=color,
            title=(
                f"Source: {data.get('source_file', 'unknown')}\n"
                f"Type: {data.get('file_type', 'unknown')}\n"
                f"Community: {community_labels.get(cid, str(cid)) if community_labels else cid}"
            ),
        )

    for u, v, data in G.edges(data=True):
        confidence = data.get("confidence", "EXTRACTED")
        width = {"EXTRACTED": 2, "INFERRED": 1, "AMBIGUOUS": 1}.get(confidence, 1)
        net.add_edge(
            u, v,
            title=f"{data.get('relation', '')} [{confidence}]",
            width=width,
            dashes=(confidence != "EXTRACTED"),
        )

    net.save_graph(output_path)

    # Inject community legend into saved HTML
    if community_labels:
        legend_items = ""
        for cid in sorted(community_labels.keys()):
            color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
            label = community_labels[cid]
            n_nodes = len(communities.get(cid, []))
            legend_items += (
                f'<div style="margin:4px 0">'
                f'<span style="color:{color};font-size:18px">■</span> '
                f'<span style="font-size:13px">{label} ({n_nodes})</span>'
                f'</div>'
            )
        legend_html = (
            '<div style="position:fixed;top:10px;right:10px;background:#2a2a4e;'
            'padding:12px 16px;border-radius:8px;font-family:sans-serif;color:white;'
            'z-index:9999;min-width:180px;">'
            '<b style="font-size:14px">Communities</b><br>'
            + legend_items +
            '</div>'
        )
        content = Path(output_path).read_text()
        content = content.replace("</body>", legend_html + "\n</body>")
        Path(output_path).write_text(content)
