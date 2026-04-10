# rootly-graphify

This project turns Rootly incident data into a knowledge graph. The Rootly corpus lives in `graphify-rootly-data/` and the graph output in `graphify-out/`.

**Always-on rules:**
- Before answering incident or architecture questions, read `graphify-out/GRAPH_REPORT.md` for god nodes and community structure
- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files
- After modifying code files, run: `python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current

---

# graphify pipeline — full instructions

When the user asks you to run graphify on a path (e.g. "run graphify on graphify-rootly-data"), follow these steps in order.

## Usage patterns

```
graphify <path>                  # full pipeline
graphify <path> --mode deep      # richer INFERRED edges
graphify <path> --update         # re-extract only new/changed files
graphify query "<question>"      # BFS traversal of graph.json
graphify path "NodeA" "NodeB"    # shortest path between two nodes
graphify explain "NodeName"      # explain a single node
```

---

## Step 1 — Ensure graphify is installed

```bash
python -c "import graphify" 2>/dev/null || pip install graphifyy -q
```

---

## Step 2 — Detect files

```bash
python -c "
import json
from graphify.detect import detect
from pathlib import Path
result = detect(Path('INPUT_PATH'))
Path('.graphify_detect.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(result['total_files'], 'files,', result['total_words'], 'words')
for k, v in result.get('files', {}).items():
    if v: print(f'  {k}: {len(v)} files')
"
```

Replace INPUT_PATH with the actual path. Present a clean summary:
```
Corpus: X files · ~Y words
  docs:   N files
  code:   N files
```

- If `total_files` is 0: stop with "No supported files found."
- If `total_words` > 2,000,000 OR `total_files` > 500: warn and ask which subfolder to run on.
- Otherwise: proceed directly to Step 3.

---

## Step 3 — Extract entities and relationships

This step has two parts: **AST extraction** (code, deterministic) and **semantic extraction** (LLM, costs tokens). Run both in parallel.

### Part A — AST extraction (code files)

```bash
python -c "
import sys, json
from graphify.extract import collect_files, extract
from pathlib import Path

detect = json.loads(Path('.graphify_detect.json').read_text(encoding='utf-8'))
code_files = []
for f in detect.get('files', {}).get('code', []):
    code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

if code_files:
    result = extract(code_files)
    Path('.graphify_ast.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'AST: {len(result[\"nodes\"])} nodes, {len(result[\"edges\"])} edges')
else:
    Path('.graphify_ast.json').write_text(json.dumps({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}), encoding='utf-8')
    print('No code files - skipping AST')
"
```

### Part B — Semantic extraction (parallel subagents)

**MANDATORY: Use parallel subagents here. Reading files one-by-one is 5-10x slower.**

#### B0 — Check cache

```bash
python -c "
import json
from graphify.cache import check_semantic_cache
from pathlib import Path

detect = json.loads(Path('.graphify_detect.json').read_text(encoding='utf-8'))
all_files = [f for files in detect['files'].values() for f in files]
cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(all_files)

if cached_nodes or cached_edges or cached_hyperedges:
    Path('.graphify_cached.json').write_text(json.dumps({'nodes': cached_nodes, 'edges': cached_edges, 'hyperedges': cached_hyperedges}), encoding='utf-8')
Path('.graphify_uncached.txt').write_text('\n'.join(uncached), encoding='utf-8')
print(f'Cache: {len(all_files)-len(uncached)} hit, {len(uncached)} need extraction')
"
```

#### B1 — Split uncached files into chunks of 20-25

Load `.graphify_uncached.txt`, split into chunks. Each image gets its own chunk.

#### B2 — Dispatch ALL subagents in a single message (parallel)

Launch one subagent per chunk simultaneously. Each subagent receives this prompt:

```
You are a graphify extraction subagent. Read the files listed and extract a knowledge graph fragment.
Output ONLY valid JSON matching the schema below - no explanation, no markdown fences, no preamble.

Files (chunk CHUNK_NUM of TOTAL_CHUNKS):
FILE_LIST

Rules:
- EXTRACTED: relationship explicit in source (import, call, citation, "see §3.2")
- INFERRED: reasonable inference (shared data structure, implied dependency)
- AMBIGUOUS: uncertain - flag for review, do not omit

Doc/paper files: extract named concepts, entities, citations. Also extract rationale — WHY decisions were made. These become nodes with `rationale_for` edges.
Image files: use vision — understand what the image IS (UI layout, chart trend, diagram components).
DEEP_MODE (if --mode deep): be aggressive with INFERRED edges. Mark uncertain ones AMBIGUOUS.

Semantic similarity: if two concepts solve the same problem without a structural link, add a `semantically_similar_to` edge (INFERRED, confidence 0.6-0.95). Only when non-obvious.

Hyperedges: if 3+ nodes participate in a shared concept not captured by pairwise edges, add to `hyperedges`. Max 3 per chunk.

confidence_score REQUIRED on every edge:
- EXTRACTED: 1.0
- INFERRED: 0.6-0.9 based on evidence strength
- AMBIGUOUS: 0.1-0.3

Output exactly this JSON:
{"nodes":[{"id":"filestem_entityname","label":"Human Readable Name","file_type":"code|document|paper|image","source_file":"relative/path","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null}],"edges":[{"source":"node_id","target":"node_id","relation":"calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to|rationale_for","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0,"source_file":"relative/path","source_location":null,"weight":1.0}],"hyperedges":[{"id":"snake_case_id","label":"Human Readable Label","nodes":["node_id1","node_id2","node_id3"],"relation":"participate_in|implement|form","confidence":"EXTRACTED|INFERRED","confidence_score":0.75,"source_file":"relative/path"}],"input_tokens":0,"output_tokens":0}
```

#### B3 — Collect and merge results

After all subagents complete, write their merged output to `.graphify_semantic_new.json`, then:

```bash
python -c "
import json
from graphify.cache import save_semantic_cache
from pathlib import Path

new = json.loads(Path('.graphify_semantic_new.json').read_text(encoding='utf-8')) if Path('.graphify_semantic_new.json').exists() else {'nodes':[],'edges':[],'hyperedges':[]}
saved = save_semantic_cache(new.get('nodes', []), new.get('edges', []), new.get('hyperedges', []))
print(f'Cached {saved} files')
"
```

```bash
python -c "
import json
from pathlib import Path

cached = json.loads(Path('.graphify_cached.json').read_text(encoding='utf-8')) if Path('.graphify_cached.json').exists() else {'nodes':[],'edges':[],'hyperedges':[]}
new = json.loads(Path('.graphify_semantic_new.json').read_text(encoding='utf-8')) if Path('.graphify_semantic_new.json').exists() else {'nodes':[],'edges':[],'hyperedges':[]}

all_nodes = cached['nodes'] + new.get('nodes', [])
all_edges = cached['edges'] + new.get('edges', [])
all_hyperedges = cached.get('hyperedges', []) + new.get('hyperedges', [])
seen = set()
deduped = []
for n in all_nodes:
    if n['id'] not in seen:
        seen.add(n['id'])
        deduped.append(n)

merged = {'nodes': deduped, 'edges': all_edges, 'hyperedges': all_hyperedges,
          'input_tokens': new.get('input_tokens', 0), 'output_tokens': new.get('output_tokens', 0)}
Path('.graphify_semantic.json').write_text(json.dumps(merged, indent=2), encoding='utf-8')
print(f'Semantic: {len(deduped)} nodes, {len(all_edges)} edges')
"
```

### Part C — Merge AST + semantic

```bash
python -c "
import json
from pathlib import Path

ast = json.loads(Path('.graphify_ast.json').read_text(encoding='utf-8'))
sem = json.loads(Path('.graphify_semantic.json').read_text(encoding='utf-8'))

seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
for n in sem['nodes']:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])

merged = {
    'nodes': merged_nodes,
    'edges': ast['edges'] + sem['edges'],
    'hyperedges': sem.get('hyperedges', []),
    'input_tokens': sem.get('input_tokens', 0),
    'output_tokens': sem.get('output_tokens', 0),
}
Path('.graphify_extract.json').write_text(json.dumps(merged, indent=2), encoding='utf-8')
print(f'Merged: {len(merged_nodes)} nodes, {len(merged[\"edges\"])} edges')
"
```

---

## Step 4 — Build graph, cluster, analyze

```bash
mkdir -p graphify-out
python -c "
import json
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text(encoding='utf-8'))
detection  = json.loads(Path('.graphify_detect.json').read_text(encoding='utf-8'))

G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, 'INPUT_PATH', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding='utf-8')
to_json(G, communities, 'graphify-out/graph.json')

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods, 'surprises': surprises, 'questions': questions,
}
Path('.graphify_analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
"
```

---

## Step 5 — Label communities

Read `.graphify_analysis.json`. For each community, look at its nodes and assign a 2-5 word plain-language name. Then:

```bash
python -c "
import json
from graphify.build import build_from_json
from graphify.analyze import suggest_questions
from graphify.report import generate
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text(encoding='utf-8'))
detection  = json.loads(Path('.graphify_detect.json').read_text(encoding='utf-8'))
analysis   = json.loads(Path('.graphify_analysis.json').read_text(encoding='utf-8'))

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}

labels = LABELS_DICT  # replace with actual dict, e.g. {0: 'Elasticsearch Incidents', 1: 'Website Outages'}

questions = suggest_questions(G, communities, labels)
report = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'], detection, tokens, 'INPUT_PATH', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding='utf-8')
Path('.graphify_labels.json').write_text(json.dumps({str(k): v for k, v in labels.items()}), encoding='utf-8')
print('Report updated with labels')
"
```

---

## Step 6 — Generate HTML visualization

```bash
python -c "
import json
from graphify.build import build_from_json
from graphify.export import to_html
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text(encoding='utf-8'))
analysis   = json.loads(Path('.graphify_analysis.json').read_text(encoding='utf-8'))
labels_raw = json.loads(Path('.graphify_labels.json').read_text(encoding='utf-8')) if Path('.graphify_labels.json').exists() else {}

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
labels = {int(k): v for k, v in labels_raw.items()}

to_html(G, communities, 'graphify-out/graph.html', community_labels=labels or None)
print('graph.html written')
"
```

---

## Step 7 — Clean up and report

```bash
rm -f .graphify_detect.json .graphify_extract.json .graphify_ast.json .graphify_semantic.json .graphify_analysis.json .graphify_labels.json .graphify_python .graphify_cached.json .graphify_uncached.txt .graphify_semantic_new.json
```

Report to user:
```
Graph complete. Outputs in graphify-out/

  graph.html       - interactive graph, open in browser
  GRAPH_REPORT.md  - audit report with god nodes + communities
  graph.json       - raw graph data for further querying
```

Then paste the God Nodes, Surprising Connections, and Suggested Questions sections from GRAPH_REPORT.md. Pick the most interesting suggested question and offer to trace it.

---

## graphify query

When user asks to query the graph:

```bash
python -c "
import sys, json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
G = json_graph.node_link_graph(data, edges='links')

question = 'QUESTION'
terms = [t.lower() for t in question.split() if len(t) > 3]

scored = []
for nid, ndata in G.nodes(data=True):
    label = ndata.get('label', '').lower()
    score = sum(1 for t in terms if t in label)
    if score > 0:
        scored.append((score, nid))
scored.sort(reverse=True)
start_nodes = [nid for _, nid in scored[:3]]

if not start_nodes:
    print('No matching nodes found for:', terms)
    sys.exit(0)

subgraph_nodes = set(start_nodes)
subgraph_edges = []
frontier = set(start_nodes)
for _ in range(3):
    next_frontier = set()
    for n in frontier:
        for neighbor in G.neighbors(n):
            if neighbor not in subgraph_nodes:
                next_frontier.add(neighbor)
                subgraph_edges.append((n, neighbor))
    subgraph_nodes.update(next_frontier)
    frontier = next_frontier

def relevance(nid):
    label = G.nodes[nid].get('label', '').lower()
    return sum(1 for t in terms if t in label)

ranked = sorted(subgraph_nodes, key=relevance, reverse=True)
lines = [f'BFS | Start: {[G.nodes[n].get(\"label\",n)[:50] for n in start_nodes]} | {len(subgraph_nodes)} nodes']
for nid in ranked:
    d = G.nodes[nid]
    lines.append(f'  NODE {d.get(\"label\", nid)} [src={d.get(\"source_file\",\"\")}]')
for u, v in subgraph_edges:
    if u in subgraph_nodes and v in subgraph_nodes:
        d = G.edges.get((u,v), {})
        lines.append(f'  EDGE {G.nodes[u].get(\"label\",u)[:50]} --{d.get(\"relation\",\"\")} [{d.get(\"confidence\",\"\")}]--> {G.nodes[v].get(\"label\",v)[:50]}')
print('\n'.join(lines)[:8000])
"
```

Answer using only what the graph contains. Do not hallucinate edges.

---

## graphify path

```bash
python -c "
import json, sys
import networkx as nx
from networkx.readwrite import json_graph
from pathlib import Path

data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
G = json_graph.node_link_graph(data, edges='links')

def find_node(term):
    term = term.lower()
    scored = sorted([(sum(1 for w in term.split() if w in G.nodes[n].get('label','').lower()), n) for n in G.nodes()], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else None

src = find_node('NODE_A')
tgt = find_node('NODE_B')

if not src or not tgt:
    print('Could not find matching nodes')
    sys.exit(0)

try:
    path = nx.shortest_path(G, src, tgt)
    print(f'Shortest path ({len(path)-1} hops):')
    for i, nid in enumerate(path):
        label = G.nodes[nid].get('label', nid)
        if i < len(path) - 1:
            edge = G.edges[nid, path[i+1]]
            print(f'  {label} --{edge.get(\"relation\",\"\")}-> [{edge.get(\"confidence\",\"\")}]')
        else:
            print(f'  {label}')
except nx.NetworkXNoPath:
    print('No path found between the two nodes')
"
```

---

## graphify explain

```bash
python -c "
import json, sys
from networkx.readwrite import json_graph
from pathlib import Path

data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
G = json_graph.node_link_graph(data, edges='links')

term = 'NODE_NAME'
scored = sorted([(sum(1 for w in term.lower().split() if w in G.nodes[n].get('label','').lower()), n) for n in G.nodes()], reverse=True)
if not scored or scored[0][0] == 0:
    print(f'No node matching {term!r}')
    sys.exit(0)

nid = scored[0][1]
d = G.nodes[nid]
print(f'NODE: {d.get(\"label\", nid)}')
print(f'  source: {d.get(\"source_file\",\"unknown\")}')
print(f'  degree: {G.degree(nid)}')
print('CONNECTIONS:')
for nb in G.neighbors(nid):
    e = G.edges[nid, nb]
    print(f'  --{e.get(\"relation\",\"\")}-> {G.nodes[nb].get(\"label\",nb)} [{e.get(\"confidence\",\"\")}]')
"
```
