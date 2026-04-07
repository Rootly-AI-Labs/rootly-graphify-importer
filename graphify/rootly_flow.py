"""Orchestrator for the graphify rootly command.

Wires together:
  TUI (tui.py) → Rootly client (rootly_client.py)
               → Corpus writer (rootly_export.py)
               → Pipeline runner (rootly_runner.py)
               → Summary printer

This module is the single entry point called from __main__.py.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _mask_key(key: str) -> str:
    """Safely mask a Rootly API key for log output.

    Rootly keys start with 'rootly_' — show the prefix and last 4 chars only.
    e.g. rootly_****a1b2
    """
    if len(key) <= 11:
        return "rootly_****"
    return key[:7] + "****" + key[-4:]


def _print_summary(
    result,  # RunResult
    corpus_dir: Path,
    n_incidents: int,
    n_retrospectives: int,
) -> None:
    print()
    print("  ── Summary ─────────────────────────────")
    print(f"  Fetched {n_incidents} incident(s)")
    print(f"  Fetched {n_retrospectives} retrospective(s)")
    print(f"  Corpus saved to {corpus_dir.resolve()}")
    print()
    if result.success:
        graph_dir = result.graph_dir
        print(f"  Graphify outputs:")
        for fname in ("graph.json", "GRAPH_REPORT.md", "graph.html"):
            p = graph_dir / fname
            if p.exists():
                print(f"    {p}")
        # Optional outputs
        for fname in ("graph.svg", "graph.graphml", "cypher.txt"):
            p = graph_dir / fname
            if p.exists():
                print(f"    {p}")
        wiki = graph_dir / "wiki" / "index.md"
        if wiki.exists():
            print(f"    {wiki}")
        print()
        print("  Tip: run /graphify " + str(corpus_dir) + " in Claude Code")
        print("       for richer LLM-powered semantic extraction on top.")
    else:
        print(f"  Graph build failed: {result.error}")
        print(f"  Raw corpus is preserved at {corpus_dir.resolve()}")
        print("  You can retry with: graphify rootly --output " + str(corpus_dir))
    print()


def run_rootly_command(
    *,
    api_key_override: str | None = None,
    days_override: int | None = None,
    mode_override: str | None = None,
    output_dir_override: Path | None = None,
) -> None:
    """Entry point for `graphify rootly`. Runs the full Rootly flow."""

    # ---- collect config (TUI or flags) ----
    from graphify.tui import run_rootly_flow
    config = run_rootly_flow(
        api_key_override=api_key_override,
        days_override=days_override,
        mode_override=mode_override,
        output_dir_override=output_dir_override,
    )

    # ---- validate API key ----
    from graphify.rootly_client import validate_key, RootlyClient

    print(f"  Validating API key ({_mask_key(config.api_key)})…")
    try:
        validate_key(config.api_key)
    except PermissionError as exc:
        print(f"\n  {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n  API validation failed: {exc}", file=sys.stderr)
        print("  Continuing anyway – fetch will fail if the key is invalid.")

    # ---- fetch Rootly data ----
    client = RootlyClient(config.api_key)

    print(
        f"  Fetching incidents from {config.start_at.strftime('%Y-%m-%d')} "
        f"to {config.end_at.strftime('%Y-%m-%d')}…"
    )
    try:
        incidents = client.fetch_incidents(config.start_at, config.end_at)
    except Exception as exc:
        print(f"\n  Failed to fetch incidents: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"  Found {len(incidents)} incident(s).")

    if not incidents:
        print("  No incidents found for the selected date range.")
        print("  Writing empty manifest and exiting.")
        from graphify.rootly_export import export_rootly_corpus
        export_rootly_corpus(config.output_dir, [], [], config)
        return

    print("  Fetching retrospectives…")
    try:
        retrospectives = client.fetch_retrospectives_for_incidents(incidents)
    except Exception as exc:
        print(f"  Warning: could not fetch retrospectives: {exc}")
        retrospectives = []

    print(f"  Found {len(retrospectives)} retrospective(s).")

    # ---- write corpus ----
    from graphify.rootly_export import export_rootly_corpus
    print(f"  Writing corpus to {config.output_dir}…")
    corpus_dir = export_rootly_corpus(
        config.output_dir,
        incidents,
        retrospectives,
        config,
    )

    # ---- run graphify pipeline ----
    from graphify.rootly_runner import run_graphify
    print(f"  Running Graphify ({config.graphify_mode.name} mode)…")
    result = run_graphify(corpus_dir, config.graphify_mode)

    # ---- print summary ----
    _print_summary(result, corpus_dir, len(incidents), len(retrospectives))

    if not result.success:
        sys.exit(1)
