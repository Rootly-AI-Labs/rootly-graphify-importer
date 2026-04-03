---
name: graphify
description: Any input (code, docs, papers, notes) → knowledge graph → clustered communities → interactive HTML + GraphRAG-ready JSON + audit report
trigger: /graphify
---

# /graphify

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```
/graphify <path>                  # full pipeline
/graphify <path> --mode deep      # thorough extraction, richer relationships
/graphify <path> --cluster-only   # rerun clustering on existing .graphify/graph.json
/graphify <path> --no-viz         # skip HTML, just files + report
/graphify <path> --neo4j          # also generate .graphify/cypher.txt
/graphify query "<question>"      # ask a question against an existing graph
```

## What You Must Do When Invoked

Follow these steps in order. Do not skip steps.

### Step 1 — Install dependencies

```bash
pip install networkx graspologic pyvis tree-sitter tree-sitter-python tree-sitter-javascript -q
pip install -e . -q 2>/dev/null || true
```

### Step 2 — Detect files

Run the detector and save results:

```bash
python -c "
import sys, json
sys.path.insert(0, 'src')
from graphify.detector import detect
from pathlib import Path
result = detect(Path('INPUT_PATH'))
print(json.dumps(result, indent=2))
" > .graphify_detect.json
cat .graphify_detect.json
```

Replace INPUT_PATH with the actual path the user provided.

If the `warning` field is not null, show it to the user and ask:
> "⚠ [warning]. Continue anyway? (y/n)"
If they say no, stop and clean up.

### Step 3 — Extract entities and relationships

Read every file listed in `.graphify_detect.json`. For each file extract nodes and edges.

**Confidence rules:**
- `EXTRACTED` — relationship is explicit in the source (import, calls, see §3.2, citation)
- `INFERRED` — reasonable inference you are making (two functions sharing data structure)
- `AMBIGUOUS` — you are not sure; flag for user review

**For code files**: Identify classes, functions, modules. Structural edges (imports, calls, class membership) are EXTRACTED. Semantic/conceptual edges are INFERRED.

**For document/paper files**: Extract concepts, named entities, citations. Citation edges are EXTRACTED. Conceptual similarity edges are INFERRED.

As you read and extract from each file, print progress so the user knows what's happening:
- Before reading each file: print `[1/N] Extracting: filename`
- After finishing all files: print `Extraction complete — N nodes, M edges found`

Output `.graphify_extract.json` in this schema:
```json
{
  "nodes": [
    {
      "id": "file_stem_entity_name",
      "label": "Human Readable Name",
      "file_type": "code|document|paper",
      "source_file": "relative/path/to/file",
      "source_location": "L42 or §3.1 or null"
    }
  ],
  "edges": [
    {
      "source": "node_id",
      "target": "node_id",
      "relation": "imports|calls|implements|references|cites|conceptually_related_to",
      "confidence": "EXTRACTED|INFERRED|AMBIGUOUS",
      "source_file": "relative/path/to/file",
      "source_location": "L42 or §3.1 or null",
      "weight": 1.0
    }
  ],
  "input_tokens": 0,
  "output_tokens": 0
}
```

Write this JSON to `.graphify_extract.json`. Set `input_tokens` and `output_tokens` to your actual token usage.

### Step 4 — Build graph, cluster, analyze, generate outputs

```bash
mkdir -p .graphify
python -c "
import sys, json
sys.path.insert(0, 'src')
from graphify.graph_builder import build_from_json, total_tokens
from graphify.clusterer import cluster, score_all
from graphify.analyzer import god_nodes, surprising_connections
from graphify.reporter import generate
from graphify.exporter import to_json, to_cypher
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text())
detection  = json.loads(Path('.graphify_detect.json').read_text())

G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
tokens = {'input': extraction['input_tokens'], 'output': extraction['output_tokens']}
gods = god_nodes(G)
surprises = surprising_connections(G)
labels = {cid: 'Community ' + str(cid) for cid in communities}

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, 'INPUT_PATH')
Path('.graphify/GRAPH_REPORT.md').write_text(report)
to_json(G, communities, '.graphify/graph.json')

analysis = {'communities': {str(k): v for k, v in communities.items()}, 'cohesion': cohesion, 'gods': gods, 'surprises': surprises}
Path('.graphify_analysis.json').write_text(json.dumps(analysis, indent=2))
print('Pipeline complete')
"
```

Replace INPUT_PATH with the actual path.

### Step 5 — Label communities

Read `.graphify_analysis.json`. For each community, look at its node labels and write a 2-5 word plain-language name (e.g. "Attention Mechanism", "Training Pipeline", "Data Loading").

Rewrite `.graphify/GRAPH_REPORT.md`, replacing `"Community N"` placeholders with the real names you chose.

### Step 6 — Generate visualization (skip if --no-viz)

```bash
python -c "
import sys, json
sys.path.insert(0, 'src')
from graphify.graph_builder import build_from_json
from graphify.clusterer import cluster
from graphify.visualizer import generate_html
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text())
G = build_from_json(extraction)
communities = cluster(G)
generate_html(G, communities, '.graphify/graph.html')
print('graph.html written')
"
```

### Step 7 — Neo4j export (only if --neo4j flag)

```bash
python -c "
import sys, json
sys.path.insert(0, 'src')
from graphify.graph_builder import build_from_json
from graphify.exporter import to_cypher
from pathlib import Path

G = __import__('graphify.graph_builder', fromlist=['build_from_json']).build_from_json(
    json.loads(Path('.graphify_extract.json').read_text()))
to_cypher(G, '.graphify/cypher.txt')
print('cypher.txt written')
"
```

### Step 8 — Clean up and report

```bash
rm -f .graphify_detect.json .graphify_extract.json .graphify_analysis.json
```

Tell the user:
```
Graph complete. Outputs in .graphify/

  GRAPH_REPORT.md  — audit trail, clusters, surprising connections
  graph.html       — open in browser to explore interactively
  graph.json       — GraphRAG-ready, compatible with Microsoft GraphRAG

[paste God Nodes section from GRAPH_REPORT.md]
[paste Surprising Connections section from GRAPH_REPORT.md]
```

## For --cluster-only

Skip Steps 1–3. Load the existing graph from `.graphify/graph.json` and run Steps 4–8:

```bash
python -c "
import sys, json
sys.path.insert(0, 'src')
from graphify.graph_builder import build_from_json
from graphify.clusterer import cluster, score_all
from graphify.analyzer import god_nodes, surprising_connections
from graphify.reporter import generate
from graphify.exporter import to_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path
import os

# Load existing graph
data = json.loads(Path('.graphify/graph.json').read_text())
G = json_graph.node_link_graph(data, edges='links')

# Rebuild a minimal detection result from graph metadata
total_nodes = G.number_of_nodes()
detection = {'total_files': total_nodes, 'total_words': 99999, 'needs_graph': True, 'warning': None}
tokens = {'input': 0, 'output': 0}

communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G)
labels = {cid: 'Community ' + str(cid) for cid in communities}

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, 'INPUT_PATH')
Path('.graphify/GRAPH_REPORT.md').write_text(report)
to_json(G, communities, '.graphify/graph.json')
print('Re-clustered successfully')
"
```

Then run Steps 5–8 as normal (label communities, generate viz, clean up, report).

## For /graphify query

Load `.graphify/graph.json`. Find the nodes and edges most relevant to the question using BFS from the most relevant starting node. Answer using only what the graph contains — do not hallucinate edges. If the graph lacks enough information, say so.

## Honesty Rules

- Never invent an edge. If unsure, use AMBIGUOUS.
- Never skip the corpus check warning.
- Always show token cost in the report.
- Never hide cohesion scores behind symbols — show the raw number.
