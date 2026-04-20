#!/usr/bin/env python3
"""Validate the integrity of an OpenFlow project."""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Check OpenFlow project integrity")
    parser.add_argument("--project-dir", default=str(Path(__file__).parent.parent))
    args = parser.parse_args()

    project = Path(args.project_dir)
    modules_dir = project / "backend" / "modules"

    errors = []
    warnings = []
    modules_found = []
    parsed_manifests = []

    # Check config files
    if not (project / "config.example.yaml").exists():
        warnings.append("config.example.yaml not found at project root")
    if not (project / "config.yaml").exists():
        warnings.append("config.yaml not found — run 'python setup.py' or copy config.example.yaml")

    # Import validator from the real OpenFlow installation (not from --project-dir)
    real_root = Path(__file__).parent.parent
    sys.path.insert(0, str(real_root))
    from backend.core.validator import validate_manifest, check_module_files

    if not modules_dir.exists():
        warnings.append("No backend/modules directory found")
        print_report(errors, warnings, modules_found)
        sys.exit(0)

    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        manifest_path = mod_dir / "manifest.json"
        if not manifest_path.exists():
            errors.append(f"Module '{mod_dir.name}': missing manifest.json")
            continue

        with open(manifest_path, encoding="utf-8") as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError as e:
                errors.append(f"Module '{mod_dir.name}': invalid JSON: {e}")
                continue

        # Schema validation (delegated to validator)
        for err in validate_manifest(manifest):
            errors.append(f"Module '{mod_dir.name}': {err}")

        # File existence check (delegated to validator)
        for err in check_module_files(manifest, str(mod_dir)):
            errors.append(f"Module '{mod_dir.name}': {err}")

        # ID must match directory name
        if manifest.get("id") != mod_dir.name:
            errors.append(
                f"Module '{mod_dir.name}': id '{manifest.get('id')}' doesn't match directory"
            )

        modules_found.append(manifest.get("id", mod_dir.name))
        parsed_manifests.append(manifest)

    # Warn if 'example' field is missing
    for manifest in parsed_manifests:
        if "example" not in manifest:
            warnings.append(
                f"Module '{manifest['id']}': champ 'example' manquant (pour empty states et Paramètres)"
            )

    # Check cross-module dependencies (reuse already-parsed manifests)
    for manifest in parsed_manifests:
        for dep in manifest.get("dependencies", []):
            if dep not in modules_found:
                errors.append(
                    f"Module '{manifest['id']}': dependency '{dep}' not found"
                )

    # Invariant: every module with a "menu" field must have a frontend.
    # A frontend exists if: (a) the directory frontend/src/modules/<id>/ exists,
    # or (b) the module id appears as a key in frontend/src/routes.tsx.
    # Prevents ghost sidebar tabs that lead to blank pages.
    frontend_modules_dir = project / "frontend" / "src" / "modules"
    routes_file = project / "frontend" / "src" / "routes.tsx"
    routes_content = routes_file.read_text(encoding="utf-8") if routes_file.exists() else ""

    # Core shell modules rendered directly by frontend/src/core/ (no module dir)
    core_shell_modules = {"dashboard"}

    for manifest in parsed_manifests:
        if "menu" not in manifest:
            continue
        mod_id = manifest["id"]
        if mod_id in core_shell_modules:
            continue
        has_dir = (frontend_modules_dir / mod_id).is_dir()
        has_route = f"{mod_id}:" in routes_content  # matches MODULE_ROUTES key
        if not has_dir and not has_route:
            errors.append(
                f"Module '{mod_id}': 'menu' present in manifest but no frontend "
                f"(neither {frontend_modules_dir / mod_id} nor MODULE_ROUTES entry "
                "in routes.tsx). Create the React component or remove 'menu'."
            )

    print_report(errors, warnings, modules_found)
    sys.exit(1 if errors else 0)


def print_report(errors, warnings, modules):
    print(f"\n{'=' * 50}")
    print("OpenFlow Integrity Check")
    print(f"{'=' * 50}")
    print(f"Modules found: {len(modules)}")
    for m in modules:
        print(f"  - {m}")
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  X {e}")
        print("\nResult: FAIL")
    else:
        print("\nResult: PASS")


if __name__ == "__main__":
    main()
