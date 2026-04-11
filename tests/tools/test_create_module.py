"""Tests for tools/create_module.py."""
import json
import subprocess
import sys
import shutil
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent.parent
CREATE_SCRIPT = PROJECT_DIR / "tools" / "create_module.py"
SCHEMA_PATH = PROJECT_DIR / "tools" / "schemas" / "manifest.schema.json"


def run_create(module_id, project_dir, extra_args=None):
    cmd = [
        sys.executable, str(CREATE_SCRIPT),
        module_id,
        "--project-dir", str(project_dir),
        "--name", "Test Module",
        "--description", "A test module",
    ]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def make_project(tmp_path):
    """Set up a minimal project with the schema."""
    schema_dest = tmp_path / "tools" / "schemas" / "manifest.schema.json"
    schema_dest.parent.mkdir(parents=True)
    shutil.copy(SCHEMA_PATH, schema_dest)
    return tmp_path


def test_create_module_creates_backend_files(tmp_path):
    """create_module.py should create backend directory with manifest.json, api.py, models.py."""
    project = make_project(tmp_path)
    result = run_create("my_module", project)
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

    backend_mod = project / "backend" / "modules" / "my_module"
    assert backend_mod.is_dir()
    assert (backend_mod / "manifest.json").exists()
    assert (backend_mod / "api.py").exists()
    assert (backend_mod / "models.py").exists()


def test_create_module_manifest_content(tmp_path):
    """manifest.json should have correct values matching arguments."""
    project = make_project(tmp_path)
    run_create("my_module", project)

    manifest_path = project / "backend" / "modules" / "my_module" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    assert manifest["id"] == "my_module"
    assert manifest["name"] == "Test Module"
    assert manifest["description"] == "A test module"
    assert manifest["version"] == "1.0.0"
    assert manifest["category"] == "custom"
    assert manifest["origin"] == "custom"
    assert "api.py" in manifest["api_routes"]
    assert "models.py" in manifest["db_models"]


def test_create_module_creates_frontend_files(tmp_path):
    """create_module.py should create frontend directory with index.tsx, components/, widgets/."""
    project = make_project(tmp_path)
    result = run_create("my_module", project)
    assert result.returncode == 0

    frontend_mod = project / "frontend" / "src" / "modules" / "my_module"
    assert frontend_mod.is_dir()
    assert (frontend_mod / "index.tsx").exists()
    assert (frontend_mod / "components").is_dir()
    assert (frontend_mod / "widgets").is_dir()


def test_create_module_index_tsx_content(tmp_path):
    """index.tsx should contain a React component with the module name."""
    project = make_project(tmp_path)
    run_create("my_module", project)

    index_path = project / "frontend" / "src" / "modules" / "my_module" / "index.tsx"
    content = index_path.read_text()

    assert "MyModule" in content  # capitalized component name
    assert "Test Module" in content
    assert "A test module" in content


def test_create_module_refuses_overwrite(tmp_path):
    """create_module.py should refuse to overwrite an existing module (exit code 1)."""
    project = make_project(tmp_path)

    # Create once
    result1 = run_create("my_module", project)
    assert result1.returncode == 0

    # Try to create again — should fail
    result2 = run_create("my_module", project)
    assert result2.returncode == 1
    assert "already exists" in result2.stderr


def test_create_module_with_category_and_origin(tmp_path):
    """create_module.py should respect --category and --origin flags."""
    project = make_project(tmp_path)
    result = run_create(
        "my_module", project,
        extra_args=["--category", "standard", "--origin", "builtin"]
    )
    assert result.returncode == 0

    manifest_path = project / "backend" / "modules" / "my_module" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["category"] == "standard"
    assert manifest["origin"] == "builtin"


def test_create_module_snake_case_component_name(tmp_path):
    """index.tsx component name should be PascalCase from snake_case module id."""
    project = make_project(tmp_path)
    run_create("my_cool_module", project)

    index_path = project / "frontend" / "src" / "modules" / "my_cool_module" / "index.tsx"
    content = index_path.read_text()
    assert "MyCoolModule" in content
