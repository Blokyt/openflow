import json
import os
import tempfile
import pytest

VALID_MANIFEST = {
    "id": "test_module",
    "name": "Test Module",
    "description": "A test module",
    "version": "1.0.0",
    "origin": "builtin",
    "category": "standard",
    "dependencies": ["transactions"],
    "menu": {"label": "Test", "icon": "test", "position": 1},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}

def test_validate_valid_manifest():
    from backend.core.validator import validate_manifest
    errors = validate_manifest(VALID_MANIFEST)
    assert errors == []

def test_validate_missing_required_field():
    from backend.core.validator import validate_manifest
    bad = {k: v for k, v in VALID_MANIFEST.items() if k != "id"}
    errors = validate_manifest(bad)
    assert len(errors) > 0
    assert any("id" in e for e in errors)

def test_validate_bad_id_format():
    from backend.core.validator import validate_manifest
    bad = {**VALID_MANIFEST, "id": "BadId"}
    errors = validate_manifest(bad)
    assert len(errors) > 0

def test_validate_bad_version_format():
    from backend.core.validator import validate_manifest
    bad = {**VALID_MANIFEST, "version": "v1"}
    errors = validate_manifest(bad)
    assert len(errors) > 0

def test_validate_manifest_file():
    from backend.core.validator import validate_manifest_file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(VALID_MANIFEST, f)
        path = f.name
    errors = validate_manifest_file(path)
    assert errors == []
    os.unlink(path)

def test_check_module_files_exist():
    from backend.core.validator import check_module_files
    with tempfile.TemporaryDirectory() as tmpdir:
        errors = check_module_files(VALID_MANIFEST, tmpdir)
        assert len(errors) > 0
        assert any("api.py" in e for e in errors)
