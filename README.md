# rootly-graphify

A Rootly-first incident knowledge graph tool. Connect the Rootly API, collect incidents, alerts, and teams for a selected time window, export them into a local corpus, and turn that corpus into a queryable knowledge graph. Use `graphify rootly` for collection and `/graphify` in Claude Code or Codex when you want deeper semantic analysis on top.

---

## Install

```bash
pip install "graphifyy[rootly]"
```

**Claude Code:**
```bash
graphify install
```

**Codex:**
```bash
graphify install --platform codex
```

---

## Set your Rootly API key

Create a `.env` file in your project root:

```dotenv
ROOTLY_API_KEY=rootly_...
```

---

## Run the workflow

### Step 1 — Fetch and build *(terminal)*

Fetches incidents, triggered alerts, and teams. Builds the initial graph with severity colors, alert filters, and team/service layers.

```bash
graphify rootly
```

Non-interactive:
```bash
graphify rootly --api-key-env ROOTLY_API_KEY --days 30 --mode standard
```

Outputs written to `graphify-rootly-data/graphify-out/`:
- `graph.html` — open in browser to explore the graph
- `GRAPH_REPORT.md` — god nodes, communities, suggested questions
- `graph.json` — raw graph for querying

---

### Step 2 — Add semantic meaning *(agent)*

Runs parallel subagents over the incident corpus to infer cross-incident themes, recurring patterns, and root cause relationships.

**Claude Code** — type in the chat:
```
/graphify graphify-rootly-data --mode deep
```

**Codex** — type in the chat:
```
run graphify on graphify-rootly-data --mode deep
```


---

### Step 3 — Re-apply Rootly colors *(terminal)*

After semantic enrichment, restore the Rootly-specific visualization with severity colors, triggered alert toggles, and team/service layers.

```bash
graphify rootly viz
```

---

## What gets collected

| Resource | What | Filter |
|---|---|---|
| Incidents | Title, severity, status, timeline, services, teams, description | Date window (`--days`) |
| Alerts | Summary, status, source, noise flag, timeline | Triggered only (linked to an incident) |
| Teams | Name, slug, service ownership | All teams in account |

---

## Visualization filters

Once `graph.html` is open in a browser:

- **Team** — filter all nodes to a specific team's incidents and services
- **Severity** — show/hide by SEV1–SEV4
- **Incidents** — all or open only
- **Alerts** — triggered (on by default) / orphaned (off by default, not collected)
- **Time range** — slider to narrow the incident window

---

## How it works

`rootly-graphify` has a Rootly collection phase and a graph analysis phase.

1. **Deterministic Rootly collection.** Validate the API key, choose a 7, 30, or 90 day window, fetch incidents whose `started_at` falls inside that window, fetch their triggered alerts via the per-incident sub-resource, fetch all team data, and write everything to a local corpus directory.

2. **Initial Rootly graph build.** The built-in Rootly runner creates nodes for incidents, alerts, teams, and services, wires them together with typed edges (`triggered`, `affects`, `owns`, `responded_by`, `targets`), clusters the graph, and writes `graph.html`, `GRAPH_REPORT.md`, and `graph.json`. The HTML includes severity color coding, team/service layers, and alert filters.

3. **Optional deep enrichment.** Run `/graphify ./graphify-rootly-data --mode deep` to dispatch parallel subagents over the markdown files and infer cross-incident themes, rationale, and conceptual links.

4. **Re-apply Rootly visualization.** After semantic enrichment the generic extractor replaces `graph.html`. Run `graphify rootly viz` to regenerate it with the full Rootly color scheme and filters applied to the enriched graph.

**Clustering is graph-topology-based — no embeddings.** Leiden finds communities by edge density. Semantic similarity edges (`semantically_similar_to`, marked `INFERRED`) influence community detection directly. No separate embedding step or vector database required.

Every relationship is tagged `EXTRACTED` (found directly in source), `INFERRED` (reasonable inference, with a confidence score), or `AMBIGUOUS` (flagged for review).

---

## What you get

**God nodes** — highest-degree incidents or services (what everything connects through)

**Surprising connections** — cross-incident links ranked by composite score, each with a plain-English explanation

**Suggested questions** — 4–5 questions the graph is uniquely positioned to answer about your incident history

**Confidence scores** — every `INFERRED` edge has a `confidence_score` (0.0–1.0). `EXTRACTED` edges are always 1.0.

**Semantic similarity edges** — cross-incident conceptual links with no structural connection. Two incidents caused by the same root pattern without sharing services or teams.

**Token efficiency** — the first run extracts and builds the graph (costs tokens). Every subsequent query reads the compact graph instead of raw markdown — that's where the savings compound. SHA256 cache means re-runs only re-process changed files.

---

## Usage

```text
# --- Rootly workflow (terminal) ---
graphify rootly                                        # interactive Rootly import flow
graphify rootly --days 30                              # collect last 30 days of incidents
graphify rootly --api-key-env ROOTLY_API_KEY           # non-interactive key lookup from env
graphify rootly --output ./my-rootly-corpus            # write corpus to a custom folder
graphify rootly viz                                    # re-apply Rootly coloring after semantic enrichment
graphify rootly viz --graph ./corpus/graphify-out/graph.json

# --- Semantic enrichment (agent: Claude Code / Codex) ---
/graphify ./graphify-rootly-data                       # analyze the Rootly corpus
/graphify ./graphify-rootly-data --mode deep           # more aggressive INFERRED edges
/graphify ./graphify-rootly-data --update              # re-extract only changed files

# --- Query the graph (agent) ---
/graphify query "which services have the most recurring incidents?"
/graphify query "what patterns connect the SEV1 incidents?"
/graphify path "payment-api" "auth-service"
/graphify explain "Incident: Database connection pool exhausted"

# --- Optional exports ---
/graphify ./graphify-rootly-data --wiki                # agent-crawlable wiki per community
/graphify ./graphify-rootly-data --no-viz              # skip HTML, report + JSON only
/graphify ./graphify-rootly-data --obsidian            # Obsidian vault

# --- Always-on assistant instructions ---
graphify claude install                                # CLAUDE.md + PreToolUse hook (Claude Code)
graphify codex install                                 # AGENTS.md (Codex)
```

---

## Re-run on new data

```bash
# Fetch fresh data and rebuild
graphify rootly --api-key-env ROOTLY_API_KEY --days 30 --mode standard

# Re-enrich with semantic step (Claude Code)
/graphify graphify-rootly-data --update

# Restore Rootly colors
graphify rootly viz
```

---

Cloned from [graphify](https://github.com/safishamsi/graphify)
