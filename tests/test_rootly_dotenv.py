"""Tests for .env loading in graphify.tui.

No network, no questionary prompts, no FS side effects outside tmp_path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.tui import _load_dotenv, resolve_api_key_from_env


# ---------------------------------------------------------------------------
# _load_dotenv
# ---------------------------------------------------------------------------

def test_load_dotenv_basic(tmp_path):
    (tmp_path / ".env").write_text("ROOTLY_API_KEY=rootly_abc123\n", encoding="utf-8")
    result = _load_dotenv(tmp_path / ".env")
    assert result["ROOTLY_API_KEY"] == "rootly_abc123"


def test_load_dotenv_double_quotes(tmp_path):
    (tmp_path / ".env").write_text('ROOTLY_API_KEY="rootly_abc123"\n', encoding="utf-8")
    result = _load_dotenv(tmp_path / ".env")
    assert result["ROOTLY_API_KEY"] == "rootly_abc123"


def test_load_dotenv_single_quotes(tmp_path):
    (tmp_path / ".env").write_text("ROOTLY_API_KEY='rootly_abc123'\n", encoding="utf-8")
    result = _load_dotenv(tmp_path / ".env")
    assert result["ROOTLY_API_KEY"] == "rootly_abc123"


def test_load_dotenv_export_prefix(tmp_path):
    (tmp_path / ".env").write_text("export ROOTLY_API_KEY=rootly_abc123\n", encoding="utf-8")
    result = _load_dotenv(tmp_path / ".env")
    assert result["ROOTLY_API_KEY"] == "rootly_abc123"


def test_load_dotenv_skips_comments(tmp_path):
    content = "# This is a comment\nROOTLY_API_KEY=rootly_abc123\n# Another comment\n"
    (tmp_path / ".env").write_text(content, encoding="utf-8")
    result = _load_dotenv(tmp_path / ".env")
    assert result["ROOTLY_API_KEY"] == "rootly_abc123"
    assert len(result) == 1  # no comment lines leaking in


def test_load_dotenv_skips_blank_lines(tmp_path):
    content = "\n\nROOTLY_API_KEY=rootly_abc123\n\n"
    (tmp_path / ".env").write_text(content, encoding="utf-8")
    result = _load_dotenv(tmp_path / ".env")
    assert result["ROOTLY_API_KEY"] == "rootly_abc123"


def test_load_dotenv_multiple_keys(tmp_path):
    content = "ROOTLY_API_KEY=rootly_abc123\nOTHER_KEY=some_value\n"
    (tmp_path / ".env").write_text(content, encoding="utf-8")
    result = _load_dotenv(tmp_path / ".env")
    assert result["ROOTLY_API_KEY"] == "rootly_abc123"
    assert result["OTHER_KEY"] == "some_value"


def test_load_dotenv_missing_file(tmp_path):
    result = _load_dotenv(tmp_path / ".env")
    assert result == {}


def test_load_dotenv_value_with_equals_sign(tmp_path):
    """Values containing = (e.g. base64 tokens) should be preserved."""
    (tmp_path / ".env").write_text("ROOTLY_API_KEY=rootly_abc==\n", encoding="utf-8")
    result = _load_dotenv(tmp_path / ".env")
    assert result["ROOTLY_API_KEY"] == "rootly_abc=="


# ---------------------------------------------------------------------------
# resolve_api_key_from_env
# ---------------------------------------------------------------------------

def test_resolve_prefers_shell_env_over_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ROOTLY_API_KEY=rootly_from_dotenv\n", encoding="utf-8")
    monkeypatch.setenv("ROOTLY_API_KEY", "rootly_from_shell")

    # Temporarily change cwd to tmp_path so _load_dotenv finds the .env
    monkeypatch.chdir(tmp_path)
    key = resolve_api_key_from_env()
    assert key == "rootly_from_shell"


def test_resolve_falls_back_to_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ROOTLY_API_KEY=rootly_from_dotenv\n", encoding="utf-8")
    monkeypatch.delenv("ROOTLY_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    key = resolve_api_key_from_env()
    assert key == "rootly_from_dotenv"


def test_resolve_returns_empty_when_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv("ROOTLY_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here

    key = resolve_api_key_from_env()
    assert key == ""


def test_resolve_accepts_explicit_dotenv_path(tmp_path, monkeypatch):
    custom = tmp_path / "custom.env"
    custom.write_text("ROOTLY_API_KEY=rootly_custom\n", encoding="utf-8")
    monkeypatch.delenv("ROOTLY_API_KEY", raising=False)

    key = resolve_api_key_from_env(dotenv_path=custom)
    assert key == "rootly_custom"
