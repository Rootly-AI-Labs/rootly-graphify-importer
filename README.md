# graphify

Any input → knowledge graph → clustered communities → interactive HTML + GraphRAG-ready JSON + audit report.

```
┌──────────────────┐         ┌────────────────────────────────────────┐
│                  │         │  .graphify/                            │
│  /graphify ./raw │  ───▶   │  ├── GRAPH_REPORT.md  # primary       │
│                  │         │  ├── graph.html        # interactive   │
│                  │         │  └── graph.json        # GraphRAG-ready│
└──────────────────┘         └────────────────────────────────────────┘
```

## Why this exists

Every other graph tool handles codebases only, builds edges silently (you can't tell what was extracted vs invented), and gives you a graph with no explanation of what it means.

graphify handles any input, tags every edge `[EXTRACTED]`, `[INFERRED]`, or `[AMBIGUOUS]`, scores cluster quality as a plain number (not an emoji), and tells you when your corpus is small enough that you don't need a graph at all.

## Install

```bash
npx skills add safishamsi/graphify/skills/graphify
```

## Usage

```bash
/graphify ./raw                    # full pipeline
/graphify ./my-repo --mode deep    # thorough extraction
/graphify ./docs --no-viz          # skip HTML
/graphify ./raw --neo4j            # also export Cypher for Neo4j
/graphify query "what connects auth to the database?"
```

Works with any mix of file types:
- `.py / .ts / .js / .go` etc → code (AST + semantic)
- `.md / .txt / .rst` → documents
- `.pdf` → papers (with citation mining)

## What you get

```
.graphify/
├── GRAPH_REPORT.md    # Corpus check · God nodes · Surprising connections ·
│                      # Community summaries with cohesion scores · Ambiguous edges
├── graph.html         # Interactive pyvis — color by community, hover for edge type
└── graph.json         # NetworkX node-link format, compatible with MS GraphRAG
```

## What this will NOT do

- Won't guarantee extraction correctness — `[AMBIGUOUS]` edges are yours to review
- Won't claim the graph is useful when it isn't — corpus < 50K words gets a warning
- Won't connect to external services unless you pass `--neo4j`
- Won't visualize graphs > 5,000 nodes — use `--no-viz` at that scale

## Design principles

Informed by Karpathy's /raw folder workflow and his observation that most RAG infrastructure is overkill. The graph earns its complexity.

1. Extraction quality is everything — clustering is downstream of it
2. Show the numbers — cohesion is 0.91, not "good"
3. The best output is what you didn't know — Surprising Connections is not optional
4. Token cost is always visible
