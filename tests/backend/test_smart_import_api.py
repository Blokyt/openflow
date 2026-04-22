"""Tests for smart_import stale temp file cleanup."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Unit tests for cleanup_stale_temps helper
# ---------------------------------------------------------------------------

def test_cleanup_stale_temps_removes_old_file(tmp_path):
    """Files older than 1 hour should be removed by cleanup_stale_temps."""
    from backend.modules.smart_import.api import cleanup_stale_temps

    old_file = tmp_path / "old_import.xlsx"
    old_file.write_bytes(b"fake xlsx content")

    # Back-date the mtime by 2 hours (7200 seconds)
    old_mtime = time.time() - 7200
    os.utime(old_file, (old_mtime, old_mtime))

    cleanup_stale_temps(temp_dir=tmp_path)

    assert not old_file.exists(), "File older than 1h should have been deleted"


def test_cleanup_stale_temps_keeps_recent_file(tmp_path):
    """Files created recently (< 1 hour) should NOT be removed."""
    from backend.modules.smart_import.api import cleanup_stale_temps

    recent_file = tmp_path / "recent_import.xlsx"
    recent_file.write_bytes(b"fake xlsx content")
    # mtime is now — very recent

    cleanup_stale_temps(temp_dir=tmp_path)

    assert recent_file.exists(), "File younger than 1h should NOT be deleted"


def test_cleanup_stale_temps_removes_only_old_files(tmp_path):
    """Mixed directory: only old files are removed, recent ones survive."""
    from backend.modules.smart_import.api import cleanup_stale_temps

    old_file = tmp_path / "old.csv"
    old_file.write_bytes(b"data")
    old_mtime = time.time() - 3700  # just over 1 hour
    os.utime(old_file, (old_mtime, old_mtime))

    recent_file = tmp_path / "recent.csv"
    recent_file.write_bytes(b"data")
    # default mtime = now

    cleanup_stale_temps(temp_dir=tmp_path)

    assert not old_file.exists(), "Old file should have been removed"
    assert recent_file.exists(), "Recent file should survive"


def test_cleanup_stale_temps_empty_dir_no_error(tmp_path):
    """cleanup_stale_temps on an empty directory should not raise."""
    from backend.modules.smart_import.api import cleanup_stale_temps

    # Should complete without exception
    cleanup_stale_temps(temp_dir=tmp_path)


def test_cleanup_stale_temps_called_on_analyze(client, tmp_path, monkeypatch):
    """cleanup_stale_temps is called when /analyze is hit."""
    from backend.modules.smart_import import api as smart_api

    calls = []

    original = smart_api.cleanup_stale_temps

    def tracking_cleanup(temp_dir=None):
        calls.append(temp_dir or smart_api.TEMP_DIR)
        original(temp_dir=temp_dir)

    monkeypatch.setattr(smart_api, "cleanup_stale_temps", tracking_cleanup)

    # Send a minimal CSV file to /analyze
    import io
    fake_csv = b"date,label,amount\n2024-01-01,Test,-10.00\n"
    resp = client.post(
        "/api/smart_import/analyze",
        files={"file": ("test.csv", io.BytesIO(fake_csv), "text/csv")},
    )
    # Whether parse succeeds or not, cleanup must have been called
    assert len(calls) >= 1, "cleanup_stale_temps was not called during /analyze"


def test_cleanup_stale_temps_called_on_commit(client, monkeypatch):
    """cleanup_stale_temps is called when /commit is hit (even for 404)."""
    from backend.modules.smart_import import api as smart_api

    calls = []

    original = smart_api.cleanup_stale_temps

    def tracking_cleanup(temp_dir=None):
        calls.append(temp_dir or smart_api.TEMP_DIR)
        original(temp_dir=temp_dir)

    monkeypatch.setattr(smart_api, "cleanup_stale_temps", tracking_cleanup)

    resp = client.post("/api/smart_import/commit", json={
        "import_id": "00000000-0000-0000-0000-000000000000",
        "parser_id": "nonexistent",
    })
    # 404 is expected (no such import session), but cleanup must have been called
    assert len(calls) >= 1, "cleanup_stale_temps was not called during /commit"
