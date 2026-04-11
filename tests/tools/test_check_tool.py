"""Tests for tools/check.py."""
import json
import subprocess
import sys
import shutil
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent.parent
CHECK_SCRIPT = PROJECT_DIR / "tools" / "check.py"
SCHEMA_PATH = PROJECT_DIR / "tools" / "schemas" / "manifest.schema.json"

VALID_MANIFEST = {
    "id": "test_mod",
    "name": "Test Module",
    "description": "A test module",
    "version": "1.0.0",
    "origin": "custom",
    "category": "custom",
    "dependencies": [],
    "menu": {"label": "Test", "icon": "box", "position": 99},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}


def run_check(project_dir):
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
    )
    return result


def test_check_real_project_no_crash():
    """check.py should run on the real project without crashing (exit 0 or 1)."""
    result = run_check(PROJECT_DIR)
    assert result.returncode in (0, 1), (
        f"Unexpected exit code {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_check_empty_project_passes(tmp_path):
    """check.py should PASS on a project with no modules directory."""
    # Set up minimal structure: tools/schemas/manifest.schema.json
    schema_dest = tmp_path / "tools" / "schemas" / "manifest.schema.json"
    schema_dest.parent.mkdir(parents=True)
    shutil.copy(SCHEMA_PATH, schema_dest)

    result = run_check(tmp_path)
    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_check_valid_module_passes(tmp_path):
    """check.py should PASS for a valid module."""
    schema_dest = tmp_path / "tools" / "schemas" / "manifest.schema.json"
    schema_dest.parent.mkdir(parents=True)
    shutil.copy(SCHEMA_PATH, schema_dest)

    mod_dir = tmp_path / "backend" / "modules" / "test_mod"
    mod_dir.mkdir(parents=True)

    (mod_dir / "manifest.json").write_text(json.dumps(VALID_MANIFEST))
    (mod_dir / "api.py").write_text("# api")
    (mod_dir / "models.py").write_text("# models")

    result = run_check(tmp_path)
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "PASS" in result.stdout
    assert "test_mod" in result.stdout


def test_check_invalid_manifest_fails(tmp_path):
    """check.py should FAIL and output FAIL when manifest is invalid JSON schema."""
    schema_dest = tmp_path / "tools" / "schemas" / "manifest.schema.json"
    schema_dest.parent.mkdir(parents=True)
    shutil.copy(SCHEMA_PATH, schema_dest)

    mod_dir = tmp_path / "backend" / "modules" / "bad_mod"
    mod_dir.mkdir(parents=True)

    bad_manifest = {"id": "bad_mod", "name": "Bad"}  # Missing required fields
    (mod_dir / "manifest.json").write_text(json.dumps(bad_manifest))

    result = run_check(tmp_path)
    assert result.returncode == 1
    assert "FAIL" in result.stdout


def test_check_missing_api_route_fails(tmp_path):
    """check.py should FAIL when an api_route file is declared but missing."""
    schema_dest = tmp_path / "tools" / "schemas" / "manifest.schema.json"
    schema_dest.parent.mkdir(parents=True)
    shutil.copy(SCHEMA_PATH, schema_dest)

    mod_dir = tmp_path / "backend" / "modules" / "test_mod"
    mod_dir.mkdir(parents=True)

    manifest = {**VALID_MANIFEST, "api_routes": ["api.py", "extra_routes.py"]}
    (mod_dir / "manifest.json").write_text(json.dumps(manifest))
    (mod_dir / "api.py").write_text("# api")
    # models.py exists, but extra_routes.py does not
    (mod_dir / "models.py").write_text("# models")

    result = run_check(tmp_path)
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "extra_routes.py" in result.stdout


def test_check_id_mismatch_fails(tmp_path):
    """check.py should FAIL when manifest id doesn't match directory name."""
    schema_dest = tmp_path / "tools" / "schemas" / "manifest.schema.json"
    schema_dest.parent.mkdir(parents=True)
    shutil.copy(SCHEMA_PATH, schema_dest)

    mod_dir = tmp_path / "backend" / "modules" / "test_mod"
    mod_dir.mkdir(parents=True)

    manifest = {**VALID_MANIFEST, "id": "wrong_id"}
    (mod_dir / "manifest.json").write_text(json.dumps(manifest))
    (mod_dir / "api.py").write_text("# api")
    (mod_dir / "models.py").write_text("# models")

    result = run_check(tmp_path)
    assert result.returncode == 1
    assert "FAIL" in result.stdout


def test_check_missing_dependency_fails(tmp_path):
    """check.py should FAIL when a dependency module does not exist."""
    schema_dest = tmp_path / "tools" / "schemas" / "manifest.schema.json"
    schema_dest.parent.mkdir(parents=True)
    shutil.copy(SCHEMA_PATH, schema_dest)

    mod_dir = tmp_path / "backend" / "modules" / "test_mod"
    mod_dir.mkdir(parents=True)

    manifest = {**VALID_MANIFEST, "dependencies": ["nonexistent_dep"]}
    (mod_dir / "manifest.json").write_text(json.dumps(manifest))
    (mod_dir / "api.py").write_text("# api")
    (mod_dir / "models.py").write_text("# models")

    result = run_check(tmp_path)
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "nonexistent_dep" in result.stdout
