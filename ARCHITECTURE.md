# Architecture

rootly-graphify connects the Rootly API to the graphify knowledge graph pipeline. It has two phases: collection (Rootly API → local corpus) and graph analysis (corpus → knowledge graph).

## Pipeline

```
Rootly API  →  rootly_export  →  rootly_runner  →  cluster()  →  analyze()  →  report()  →  export()
```

## Module responsibilities

| Module | Function | Input → Output |
|--------|----------|----------------|
| `rootly_export.py` | `run_rootly_export()` | Rootly API → local corpus (markdown + JSON) |
| `rootly_runner.py` | `rootly_build_graph()` | corpus → `nx.Graph` with typed nodes and edges |
| `cluster.py` | `cluster(G)` | graph → graph with `community` attr on each node |
| `analyze.py` | `analyze(G)` | graph → analysis dict (god nodes, surprises, questions) |
| `report.py` | `render_report(G, analysis)` | graph + analysis → GRAPH_REPORT.md string |
| `export.py` | `export(G, out_dir, ...)` | graph → graph.json, graph.html |

## Rootly collection (`rootly_export.py`)

1. Validate API key (from `.env` or `--api-key-env`)
2. Prompt for time window (7, 30, or 90 days)
3. Fetch incidents whose `started_at` falls inside the window
4. Fetch triggered alerts per incident via sub-resource endpoint
5. Fetch all teams
6. Write markdown + raw JSON to corpus directory
7. Write `.graphifyignore` to exclude retrospectives from graph

## Rootly graph build (`rootly_runner.py`)

Reads incident JSON and creates a typed graph:

**Nodes:**
- Incident (labeled by title, colored by severity)
- Alert (linked to triggering incident)
- Team (organizational unit)
- Service (affected infrastructure)
- Severity level (SEV0–SEV3)

**Edges:**
- `triggered` — alert → incident
- `affects` — incident → service
- `owns` — team → service
- `responded_by` — incident → team
- `has_severity` — incident → severity
- `assigned_to_team` — incident → team

## Confidence labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Relationship directly from Rootly API data (severity, team assignment) |
| `INFERRED` | Reasonable deduction (shared service, co-occurrence) |
| `AMBIGUOUS` | Uncertain — flagged for review |

## Optional deep enrichment

Running `/graphify ./corpus --mode deep` dispatches parallel subagents over the markdown files to infer cross-incident themes, rationale, and conceptual links. This adds `INFERRED` and `semantically_similar_to` edges on top of the deterministic graph.

## Testing

```bash
pytest tests/ -q
```
