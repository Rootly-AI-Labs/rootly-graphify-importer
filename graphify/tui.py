"""Interactive TUI for the graphify rootly flow.

Uses `questionary` (built on prompt_toolkit) for a lightweight interactive
CLI.  questionary was chosen over textual because:
  - Single-file, pure Python, no curses/blessed dependency
  - Works well inside terminals that don't support full TUI (e.g. Claude Code)
  - Secure password input via questionary.password()
  - Easy to swap to textual in V2 without touching the orchestration layer

Install:  pip install graphifyy[rootly]
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graphify.models_rootly import (
        DateRangePreset,
        GraphifyMode,
        GraphifyModeName,
        RootlyFlowConfig,
    )

# ---------------------------------------------------------------------------
# .env loader (no python-dotenv dependency required)
# ---------------------------------------------------------------------------

def _load_dotenv(env_path: Path | None = None) -> dict[str, str]:
    """Parse a .env file and return a dict of key→value pairs.

    Handles the common subset of .env syntax:
    - KEY=value
    - KEY="value"  or  KEY='value'   (quotes stripped)
    - # comment lines (skipped)
    - blank lines (skipped)
    - export KEY=value  (export prefix stripped)

    Does NOT modify os.environ — callers decide what to do with the result.
    """
    path = env_path or Path.cwd() / ".env"
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip optional 'export ' prefix
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes (single or double)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key:
                result[key] = value
    except OSError:
        pass
    return result


def resolve_api_key_from_env(dotenv_path: Path | None = None) -> str:
    """Look up ROOTLY_API_KEY in this priority order:

    1. os.environ (shell export, CI secret, etc.)
    2. .env file in current working directory (or dotenv_path if given)

    Returns empty string if not found in either place.
    """
    # 1. Shell environment takes priority
    shell_key = os.environ.get("ROOTLY_API_KEY", "").strip()
    if shell_key:
        return shell_key

    # 2. .env file
    dotenv = _load_dotenv(dotenv_path)
    return dotenv.get("ROOTLY_API_KEY", "").strip()


# ---------------------------------------------------------------------------
# Lazy import guard for questionary
# ---------------------------------------------------------------------------

def _require_questionary():
    try:
        import questionary
        return questionary
    except ImportError:
        print(
            "\n  questionary is required for the interactive TUI.\n"
            "  Install it with:\n\n"
            "    pip install graphifyy[rootly]\n\n"
            "  Or non-interactively:\n\n"
            "    graphify rootly --api-key-env ROOTLY_API_KEY --days 30 --mode standard\n",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Individual prompt steps
# ---------------------------------------------------------------------------

def prompt_api_key() -> tuple[str, bool]:
    """Return (api_key, use_env_key).

    Resolution priority:
    1. ROOTLY_API_KEY already set in shell environment
    2. ROOTLY_API_KEY found in .env file in the current working directory
    3. Interactive masked input (fallback)

    In cases 1 and 2 the user is shown where the key came from and asked to
    confirm, so there are no silent surprises.
    """
    q = _require_questionary()

    # Check shell env first, then .env file
    shell_key = os.environ.get("ROOTLY_API_KEY", "").strip()
    dotenv_key = ""
    dotenv_source = ""

    if not shell_key:
        dotenv = _load_dotenv()
        dotenv_key = dotenv.get("ROOTLY_API_KEY", "").strip()
        if dotenv_key:
            dotenv_source = str(Path.cwd() / ".env")

    auto_key = shell_key or dotenv_key
    if auto_key:
        source_label = (
            "shell environment ($ROOTLY_API_KEY)"
            if shell_key
            else f".env file ({dotenv_source})"
        )
        masked = auto_key[:7] + "****" + auto_key[-4:] if len(auto_key) > 11 else "rootly_****"
        use_auto = q.confirm(
            f"Use ROOTLY_API_KEY from {source_label}?\n  Key: {masked}",
            default=True,
        ).ask()
        if use_auto:
            return auto_key, True

    key = q.password("Paste your Rootly API key:").ask()
    if not key or not key.strip():
        print("  No API key entered – aborting.", file=sys.stderr)
        sys.exit(1)
    return key.strip(), False


def prompt_date_range() -> "DateRangePreset":
    """Return one of '7d', '30d', '90d'."""
    q = _require_questionary()

    label_to_preset = {
        "Past 7 days":  "7d",
        "Past 30 days": "30d",
        "Past 90 days": "90d",
    }
    choice = q.select(
        "Choose date range:",
        choices=list(label_to_preset.keys()),
    ).ask()
    if choice is None:
        sys.exit(0)
    return label_to_preset[choice]  # type: ignore[return-value]


_PRIMARY_MODES: list[tuple[str, str]] = [
    ("Standard  – /graphify <corpus>", "standard"),
    ("Deep      – /graphify <corpus> --mode deep", "deep"),
    ("No viz    – /graphify <corpus> --no-viz", "no_viz"),
    ("Obsidian  – /graphify <corpus> --obsidian", "obsidian"),
    ("Update    – /graphify <corpus> --update", "update"),
    ("More details…", "__more__"),
]

_ADVANCED_FLAGS: list[tuple[str, str, str]] = [
    # (label, flag, description)
    ("--watch",   "--watch",   "Auto-rebuild as files change"),
    ("--wiki",    "--wiki",    "Generate Obsidian vault"),
    ("--svg",     "--svg",     "Export SVG"),
    ("--graphml", "--graphml", "Export GraphML (Gephi / yEd)"),
    ("--neo4j",   "--neo4j",   "Export Cypher queries"),
]


def prompt_run_mode() -> "GraphifyMode":
    """Return a GraphifyMode. Shows primary modes then 'More details' expansion."""
    from graphify.models_rootly import GraphifyMode

    q = _require_questionary()

    label_to_name: dict[str, str] = {label: name for label, name in _PRIMARY_MODES}

    choice = q.select(
        "Choose Graphify run mode:",
        choices=[label for label, _ in _PRIMARY_MODES],
    ).ask()
    if choice is None:
        sys.exit(0)

    name = label_to_name[choice]
    if name != "__more__":
        return GraphifyMode.from_name(name)  # type: ignore[arg-type]

    # ---- More details ----
    return _prompt_advanced_mode(q)


def _prompt_advanced_mode(q) -> "GraphifyMode":
    """Show expanded advanced options and build a GraphifyMode with extra flags."""
    from graphify.models_rootly import GraphifyMode

    # Step 1: pick base mode
    base_labels = [label for label, name in _PRIMARY_MODES if name != "__more__"]
    base_choice = q.select("Base run mode:", choices=base_labels).ask()
    if base_choice is None:
        sys.exit(0)

    base_name = {label: name for label, name in _PRIMARY_MODES}[base_choice]

    # Step 2: pick additional export flags (multi-select)
    extra_choices = q.checkbox(
        "Additional export options (space to select, enter to confirm):",
        choices=[
            q.Choice(title=f"{flag}  – {desc}", value=flag)
            for flag, _, desc in _ADVANCED_FLAGS
        ],
    ).ask()
    if extra_choices is None:
        extra_choices = []

    mode = GraphifyMode.from_name(base_name)  # type: ignore[arg-type]
    # Merge in the extra flags without duplicating what the base already has
    for flag in extra_choices:
        if flag not in mode.extra_flags:
            mode.extra_flags.append(flag)

    return mode


def prompt_output_dir(default: Path) -> Path:
    """Ask where to write the Rootly corpus. Returns the chosen Path."""
    q = _require_questionary()

    raw = q.text(
        "Output directory for Rootly corpus:",
        default=str(default),
    ).ask()
    if raw is None:
        sys.exit(0)
    return Path(raw.strip() or str(default))


# ---------------------------------------------------------------------------
# Security warning
# ---------------------------------------------------------------------------

def prompt_data_types() -> tuple[bool, bool, bool]:
    """Ask which data types to collect. Returns (incidents, alerts, teams)."""
    q = _require_questionary()

    choices = q.checkbox(
        "Select data to collect:",
        choices=[
            q.Choice(title="Incidents  – full date-window fetch", value="incidents", checked=True),
            q.Choice(title="Alerts     – triggered only (linked to an incident)", value="alerts", checked=True),
            q.Choice(title="Teams      – full account fetch", value="teams", checked=True),
        ],
    ).ask()

    if choices is None:
        sys.exit(0)
    if not choices:
        print("  No data types selected – aborting.", file=sys.stderr)
        sys.exit(1)

    return "incidents" in choices, "alerts" in choices, "teams" in choices


def print_data_warning() -> None:
    print()
    print("  WARNING: Rootly data may contain sensitive incident information.")
    print("  The export directory will be added to .gitignore automatically.")
    print("  Do not commit it to version control.")
    print()


# ---------------------------------------------------------------------------
# Top-level flow entry point
# ---------------------------------------------------------------------------

def run_rootly_flow(
    *,
    api_key_override: str | None = None,
    days_override: int | None = None,
    mode_override: str | None = None,
    output_dir_override: Path | None = None,
    data_override: str | None = None,
) -> "RootlyFlowConfig":
    """Run the interactive TUI and return a fully-populated RootlyFlowConfig.

    Any ``_override`` parameter short-circuits the corresponding TUI step,
    enabling non-interactive automation.
    """
    from graphify.models_rootly import GraphifyMode, RootlyFlowConfig
    from graphify.rootly_client import date_range_to_datetimes

    print()
    print("  Graphify – Rootly Import")
    print("  ─────────────────────────")

    # ---- API key ----
    # api_key_override comes from --api-key-env flag (already resolved by __main__).
    # When not provided, prompt_api_key() checks shell env + .env file before prompting.
    if api_key_override:
        api_key, use_env_key = api_key_override, True
    else:
        api_key, use_env_key = prompt_api_key()

    # ---- date range ----
    if days_override is not None:
        preset_map = {7: "7d", 30: "30d", 90: "90d"}
        preset = preset_map.get(days_override)
        if preset is None:
            print(
                f"  Invalid --days value {days_override}. Choose 7, 30, or 90.",
                file=sys.stderr,
            )
            sys.exit(1)
        date_range_preset = preset  # type: ignore[assignment]
    else:
        date_range_preset = prompt_date_range()

    # ---- run mode ----
    if mode_override:
        _valid = {"standard", "deep", "update", "cluster_only", "no_viz", "obsidian"}
        if mode_override not in _valid:
            print(f"  Invalid --mode '{mode_override}'. Choose from: {', '.join(sorted(_valid))}", file=sys.stderr)
            sys.exit(1)
        graphify_mode = GraphifyMode.from_name(mode_override)  # type: ignore[arg-type]
    else:
        graphify_mode = prompt_run_mode()

    # ---- output dir ----
    default_output = Path("graphify-rootly-data")
    if output_dir_override:
        output_dir = output_dir_override
    else:
        output_dir = prompt_output_dir(default_output)

    # ---- data types ----
    if data_override is not None:
        parts = {p.strip().lower() for p in data_override.split(",")}
        collect_incidents = "incidents" in parts
        collect_alerts    = "alerts" in parts
        collect_teams     = "teams" in parts
        if not collect_incidents and not collect_alerts and not collect_teams:
            print("  --data must include at least one of: incidents, alerts, teams", file=sys.stderr)
            sys.exit(1)
    else:
        collect_incidents, collect_alerts, collect_teams = prompt_data_types()

    # ---- compute date window ----
    start_at, end_at = date_range_to_datetimes(date_range_preset)  # type: ignore[arg-type]

    print_data_warning()

    return RootlyFlowConfig(
        api_key=api_key,
        date_range_preset=date_range_preset,  # type: ignore[arg-type]
        start_at=start_at,
        end_at=end_at,
        output_dir=output_dir,
        graphify_mode=graphify_mode,
        use_env_key=use_env_key,
        collect_incidents=collect_incidents,
        collect_alerts=collect_alerts,
        collect_teams=collect_teams,
    )
