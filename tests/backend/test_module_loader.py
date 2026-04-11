import json
import os
import tempfile
import pytest

VALID_MANIFEST = {
    "id": "fake_module",
    "name": "Fake Module",
    "description": "For testing",
    "version": "1.0.0",
    "origin": "builtin",
    "category": "core",
    "dependencies": [],
    "menu": {"label": "Fake", "icon": "fake", "position": 1},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}

def _create_module(base_dir: str, manifest: dict):
    mod_dir = os.path.join(base_dir, manifest["id"])
    os.makedirs(mod_dir, exist_ok=True)
    with open(os.path.join(mod_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    for route in manifest.get("api_routes", []):
        open(os.path.join(mod_dir, route), "w").close()
    for model in manifest.get("db_models", []):
        open(os.path.join(mod_dir, model), "w").close()

def test_discover_modules():
    from backend.core.module_loader import discover_modules
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_module(tmpdir, VALID_MANIFEST)
        _create_module(tmpdir, {**VALID_MANIFEST, "id": "another_module"})
        modules = discover_modules(tmpdir)
        assert len(modules) == 2
        ids = {m["id"] for m in modules}
        assert "fake_module" in ids
        assert "another_module" in ids

def test_filter_active_modules():
    from backend.core.module_loader import discover_modules, filter_active
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_module(tmpdir, VALID_MANIFEST)
        _create_module(tmpdir, {**VALID_MANIFEST, "id": "inactive_mod"})
        all_modules = discover_modules(tmpdir)
        active_config = {"fake_module": True, "inactive_mod": False}
        active = filter_active(all_modules, active_config)
        assert len(active) == 1
        assert active[0]["id"] == "fake_module"

def test_check_dependencies_satisfied():
    from backend.core.module_loader import check_dependencies
    manifests = [
        {**VALID_MANIFEST, "id": "transactions", "dependencies": []},
        {**VALID_MANIFEST, "id": "invoices", "dependencies": ["transactions"]},
    ]
    errors = check_dependencies(manifests)
    assert errors == []

def test_check_dependencies_missing():
    from backend.core.module_loader import check_dependencies
    manifests = [
        {**VALID_MANIFEST, "id": "invoices", "dependencies": ["transactions"]},
    ]
    errors = check_dependencies(manifests)
    assert len(errors) > 0
    assert any("transactions" in e for e in errors)

def test_detect_route_conflicts():
    from backend.core.module_loader import detect_route_conflicts
    manifests = [
        {**VALID_MANIFEST, "id": "mod_a", "api_routes": ["api.py"]},
        {**VALID_MANIFEST, "id": "mod_b", "api_routes": ["api.py"]},
    ]
    conflicts = detect_route_conflicts(manifests)
    assert conflicts == []
