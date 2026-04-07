# incident-graphify

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v3)](https://github.com/safishamsi/graphify/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/graphifyy)](https://pypi.org/project/graphifyy/)
[![Sponsor](https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/safishamsi)

**A Rootly-first incident knowledge graph tool.** Connect the Rootly API, collect incidents and retrospectives for a selected time window, export them into a local corpus, and turn that corpus into a queryable knowledge graph. Use `graphify rootly` for collection and `/graphify` in Claude Code, Codex, OpenCode, OpenClaw, or Factory Droid when you want deeper graph analysis inside an assistant.

This fork is optimized for incident review. It pulls the last 7, 30, or 90 days of Rootly incidents, preserves the raw incident and retrospective data locally, and surfaces the clusters, god nodes, and surprising connections across your incident history. It still works on any folder of code, docs, papers, or images, but the primary workflow starts with Rootly.

Run this in your terminal:

```bash
graphify rootly --days 30
```

```text
graphify-rootly-data/
|-- incidents/          one markdown + one raw JSON file per incident
|-- retrospectives/     one markdown + one raw JSON file per retrospective
|-- rootly-export.json  combined export
`-- graphify-out/
    |-- graph.html      interactive graph for incident exploration
    |-- GRAPH_REPORT.md god nodes, communities, and suggested questions
    `-- graph.json      persistent graph for later query/path/explain
```

Then run this in Claude Code, Codex, OpenCode, OpenClaw, or Factory Droid:

```text
/graphify ./graphify-rootly-data --mode deep
```

## How it works

`incident-graphify` has a Rootly collection phase and a graph analysis phase.

1. **Deterministic Rootly collection.** Validate the API key, choose a 7, 30, or 90 day window, fetch incidents whose `started_at` falls inside that window, fetch retrospectives linked to those incidents, and write everything to a local corpus directory.
2. **Initial Rootly graph build.** The built-in Rootly runner creates one node per incident and retrospective, links retrospectives to incidents by Incident ID, clusters the graph, and writes `graph.html`, `GRAPH_REPORT.md`, and `graph.json`.
3. **Optional deep enrichment.** Run `/graphify ./graphify-rootly-data --mode deep` on the exported corpus to dispatch parallel subagents over the markdown files and infer cross-incident themes, rationale, and conceptual links.

**Clustering is graph-topology-based - no embeddings.** Leiden finds communities by edge density. The semantic similarity edges (`semantically_similar_to`, marked `INFERRED`) are already in the graph, so they influence community detection directly. The graph structure is the similarity signal - no separate embedding step or vector database is required.

Every relationship is tagged `EXTRACTED` (found directly in source), `INFERRED` (reasonable inference, with a confidence score), or `AMBIGUOUS` (flagged for review). You always know what was found vs guessed.

## Install

**Requires:** Python 3.10+ and one of: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [OpenClaw](https://openclaw.ai), or [Factory Droid](https://factory.ai)

```bash
pip install "graphifyy[rootly]" && graphify install
```

> The PyPI package is still `graphifyy` and the CLI is still `graphify`. This README uses the product name `incident-graphify` to describe the Rootly-focused fork.

### Platform support

| Platform | Install command |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (auto-detected) or `graphify install --platform windows` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |

Codex users also need `multi_agent = true` under `[features]` in `~/.codex/config.toml` for deep semantic extraction. Factory Droid uses the `Task` tool for parallel subagent dispatch. OpenClaw uses sequential extraction (parallel agent support is still early on that platform). The basic `graphify rootly` collection flow does not require multi-agent support.

### Rootly setup

1. Install the Rootly extras and assistant integration:

   ```bash
   pip install "graphifyy[rootly]"
   graphify install
   ```

2. Provide your Rootly API key. You can either set it in your shell:

   ```powershell
   $env:ROOTLY_API_KEY="rootly_..."
   ```

   or place it in a local `.env` file:

   ```dotenv
   ROOTLY_API_KEY=rootly_...
   ```

   `graphify rootly --days 30` will read `.env` interactively if present. `--api-key-env ROOTLY_API_KEY` reads the actual environment variable.

3. Collect incidents for the time window you want:

   ```bash
   graphify rootly --days 30
   ```

   Non-interactive example:

   ```bash
   graphify rootly --api-key-env ROOTLY_API_KEY --days 30 --mode standard --output graphify-rootly-data
   ```

4. Review the generated outputs:

   - `graphify-rootly-data/graphify-out/graph.html`
   - `graphify-rootly-data/graphify-out/GRAPH_REPORT.md`
   - `graphify-rootly-data/graphify-out/graph.json`

5. Optional: rerun semantic enrichment on the exported corpus from your assistant:

   ```text
   /graphify ./graphify-rootly-data --mode deep
   ```

What `graphify rootly` does:

- Validates the Rootly API key
- Selects incidents in the chosen 7/30/90 day window using incident `started_at`
- Fetches linked retrospectives
- Exports markdown plus raw JSON locally
- Builds the initial report, graph JSON, and HTML visualization

### Make your assistant always use the graph (recommended)

After building a graph, run this once in your project:

| Platform | Command |
|----------|---------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| OpenClaw | `graphify claw install` |
| Factory Droid | `graphify droid install` |

**Claude Code** does two things: writes a `CLAUDE.md` section telling Claude to read `graphify-out/GRAPH_REPORT.md` before answering architecture questions, and installs a **PreToolUse hook** (`settings.json`) that fires before every Glob and Grep call. If a knowledge graph exists, Claude sees: _"graphify: Knowledge graph exists. Read GRAPH_REPORT.md for god nodes and community structure before searching raw files."_ — so Claude navigates via the graph instead of grepping through every file.

**Codex, OpenCode, OpenClaw, Factory Droid** write the same rules to `AGENTS.md` in your project root. These platforms don't support PreToolUse hooks, so AGENTS.md is the always-on mechanism.

Uninstall with the matching uninstall command (e.g. `graphify claude uninstall`).

**Always-on vs explicit trigger — what's the difference?**

The always-on hook surfaces `GRAPH_REPORT.md` — a one-page summary of god nodes, communities, and surprising connections. Your assistant reads this before searching files, so it navigates by structure instead of keyword matching. That covers most everyday questions.

`/graphify query`, `/graphify path`, and `/graphify explain` go deeper: they traverse the raw `graph.json` hop by hop, trace exact paths between nodes, and surface edge-level detail (relation type, confidence score, source location). Use them when you want a specific question answered from the graph rather than a general orientation.

Think of it this way: the always-on hook gives your assistant a map. The `/graphify` commands let it navigate the map precisely.

<details>
<summary>Manual install (curl)</summary>

```bash
mkdir -p ~/.claude/skills/graphify
curl -fsSL https://raw.githubusercontent.com/safishamsi/graphify/v3/graphify/skill.md \
  > ~/.claude/skills/graphify/SKILL.md
```

Add to `~/.claude/CLAUDE.md`:

```
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.
```

</details>

## Usage

```text
graphify rootly                                  # interactive Rootly import flow
graphify rootly --days 30                        # collect incidents started in the last 30 days
graphify rootly --api-key-env ROOTLY_API_KEY     # non-interactive key lookup from env
graphify rootly --output ./my-rootly-corpus      # write the exported Rootly corpus to a custom folder

/graphify ./graphify-rootly-data                 # analyze the exported Rootly corpus in your assistant
/graphify ./graphify-rootly-data --mode deep     # add more aggressive INFERRED edges across incidents and retrospectives
/graphify ./graphify-rootly-data --update        # re-extract only changed files in the exported corpus

/graphify                          # run on current directory
/graphify ./raw                    # run on a specific folder
/graphify ./raw --mode deep        # more aggressive INFERRED edge extraction
/graphify ./raw --update           # re-extract only changed files, merge into existing graph
/graphify ./raw --cluster-only     # rerun clustering on existing graph, no re-extraction
/graphify ./raw --no-viz           # skip HTML, just produce report + JSON
/graphify ./raw --obsidian         # also generate Obsidian vault (opt-in)

/graphify add https://arxiv.org/abs/1706.03762        # fetch a paper, save, update graph
/graphify add https://x.com/karpathy/status/...       # fetch a tweet
/graphify add https://... --author "Name"             # tag the original author
/graphify add https://... --contributor "Name"        # tag who added it to the corpus

/graphify query "what connects attention to the optimizer?"
/graphify query "what connects attention to the optimizer?" --dfs   # trace a specific path
/graphify query "what connects attention to the optimizer?" --budget 1500  # cap at N tokens
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

/graphify ./raw --watch            # auto-sync graph as files change (code: instant, docs: notifies you)
/graphify ./raw --wiki             # build agent-crawlable wiki (index.md + article per community)
/graphify ./raw --svg              # export graph.svg
/graphify ./raw --graphml          # export graph.graphml (Gephi, yEd)
/graphify ./raw --neo4j            # generate cypher.txt for Neo4j
/graphify ./raw --neo4j-push bolt://localhost:7687    # push directly to a running Neo4j instance
/graphify ./raw --mcp              # start MCP stdio server

# git hooks - platform-agnostic, rebuild graph on commit and branch switch
graphify hook install
graphify hook uninstall
graphify hook status

# always-on assistant instructions - platform-specific
graphify claude install            # CLAUDE.md + PreToolUse hook (Claude Code)
graphify claude uninstall
graphify codex install             # AGENTS.md (Codex)
graphify opencode install          # AGENTS.md (OpenCode)
graphify claw install              # AGENTS.md (OpenClaw)
graphify droid install             # AGENTS.md (Factory Droid)
```

Works with any mix of file types:

| Type | Extensions | Extraction |
|------|-----------|------------|
| Code | `.py .ts .js .go .rs .java .c .cpp .rb .cs .kt .scala .php .swift .lua .zig .ps1` | AST via tree-sitter + call-graph + docstring/comment rationale |
| Docs | `.md .txt .rst` | Concepts + relationships + design rationale via Claude |
| Office | `.docx .xlsx` | Converted to markdown then extracted via Claude (requires `pip install graphifyy[office]`) |
| Papers | `.pdf` | Citation mining + concept extraction |
| Images | `.png .jpg .webp .gif` | Claude vision - screenshots, diagrams, any language |

## What you get

**God nodes** - highest-degree concepts (what everything connects through)

**Surprising connections** - ranked by composite score. Code-paper edges rank higher than code-code. Each result includes a plain-English why.

**Suggested questions** - 4-5 questions the graph is uniquely positioned to answer

**The "why"** - docstrings, inline comments (`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`), and design rationale from docs are extracted as `rationale_for` nodes. Not just what the code does - why it was written that way.

**Confidence scores** - every INFERRED edge has a `confidence_score` (0.0-1.0). You know not just what was guessed but how confident the model was. EXTRACTED edges are always 1.0.

**Semantic similarity edges** - cross-file conceptual links with no structural connection. Two functions solving the same problem without calling each other, a class in code and a concept in a paper describing the same algorithm.

**Hyperedges** - group relationships connecting 3+ nodes that pairwise edges can't express. All classes implementing a shared protocol, all functions in an auth flow, all concepts from a paper section forming one idea.

**Token benchmark** - printed automatically after every run. On a mixed corpus (Karpathy repos + papers + images): **71.5x** fewer tokens per query vs reading raw files. The first run extracts and builds the graph (this costs tokens). Every subsequent query reads the compact graph instead of raw files — that's where the savings compound. The SHA256 cache means re-runs only re-process changed files.

**Auto-sync** (`--watch`) - run in a background terminal and the graph updates itself as your codebase changes. Code file saves trigger an instant rebuild (AST only, no LLM). Doc/image changes notify you to run `--update` for the LLM re-pass.

**Git hooks** (`graphify hook install`) - installs post-commit and post-checkout hooks. Graph rebuilds automatically after every commit and every branch switch. If a rebuild fails, the hook exits with a non-zero code so git surfaces the error instead of silently continuing. No background process needed.

**Wiki** (`--wiki`) - Wikipedia-style markdown articles per community and god node, with an `index.md` entry point. Point any agent at `index.md` and it can navigate the knowledge base by reading files instead of parsing JSON.
