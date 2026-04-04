"""Tests for watch.py — file watcher helpers (no watchdog required)."""
import time
from pathlib import Path
import pytest

from graphify.watch import _run_update, _WATCHED_EXTENSIONS


# --- _run_update ---

def test_run_update_creates_flag(tmp_path):
    _run_update(tmp_path)
    flag = tmp_path / ".graphify" / "needs_update"
    assert flag.exists()
    assert flag.read_text() == "1"

def test_run_update_creates_flag_dir(tmp_path):
    # .graphify dir does not exist yet
    assert not (tmp_path / ".graphify").exists()
    _run_update(tmp_path)
    assert (tmp_path / ".graphify").is_dir()

def test_run_update_idempotent(tmp_path):
    _run_update(tmp_path)
    _run_update(tmp_path)
    flag = tmp_path / ".graphify" / "needs_update"
    assert flag.read_text() == "1"


# --- _WATCHED_EXTENSIONS ---

def test_watched_extensions_includes_code():
    assert ".py" in _WATCHED_EXTENSIONS
    assert ".ts" in _WATCHED_EXTENSIONS
    assert ".go" in _WATCHED_EXTENSIONS
    assert ".rs" in _WATCHED_EXTENSIONS

def test_watched_extensions_includes_docs():
    assert ".md" in _WATCHED_EXTENSIONS
    assert ".txt" in _WATCHED_EXTENSIONS
    assert ".pdf" in _WATCHED_EXTENSIONS

def test_watched_extensions_includes_images():
    assert ".png" in _WATCHED_EXTENSIONS
    assert ".jpg" in _WATCHED_EXTENSIONS

def test_watched_extensions_excludes_noise():
    assert ".json" not in _WATCHED_EXTENSIONS
    assert ".pyc" not in _WATCHED_EXTENSIONS
    assert ".log" not in _WATCHED_EXTENSIONS


# --- watch() import error without watchdog ---

def test_watch_raises_without_watchdog(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "watchdog.observers" or name == "watchdog.events":
            raise ImportError("mocked missing watchdog")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from graphify.watch import watch
    with pytest.raises(ImportError, match="watchdog not installed"):
        watch(tmp_path)
