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
    schema_path = project / "tools" / "schemas" / "manifest.schema.json"

    errors = []
    warnings = []
    modules_found = []

    # Check config files
    config_example_path = project / "config.example.yaml"
    if not config_example_path.exists():
        warnings.append("config.example.yaml not found at project root")
    config_path = project / "config.yaml"
    if not config_path.exists():
        warnings.append("config.yaml not found — run 'python setup.py' or copy config.example.yaml")

    if not schema_path.exists():
        errors.append(f"Manifest schema not found: {schema_path}")
        print_report(errors, warnings, modules_found)
        sys.exit(1)

    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    import jsonschema

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

        validator = jsonschema.Draft202012Validator(schema)
        for error in validator.iter_errors(manifest):
            errors.append(f"Module '{mod_dir.name}': {error.message}")

        for route_file in manifest.get("api_routes", []):
            if not (mod_dir / route_file).exists():
                errors.append(f"Module '{mod_dir.name}': api_route '{route_file}' not found")
        for model_file in manifest.get("db_models", []):
            if not (mod_dir / model_file).exists():
                errors.append(f"Module '{mod_dir.name}': db_model '{model_file}' not found")

        if manifest.get("id") != mod_dir.name:
            errors.append(
                f"Module '{mod_dir.name}': id '{manifest.get('id')}' doesn't match directory"
            )

        modules_found.append(manifest.get("id", mod_dir.name))

    # Check dependencies
    for mod_dir in sorted(modules_dir.iterdir()):
        manifest_path = mod_dir / "manifest.json"
        if not manifest_path.exists() or not mod_dir.is_dir():
            continue
        with open(manifest_path, encoding="utf-8") as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError:
                continue
        for dep in manifest.get("dependencies", []):
            if dep not in modules_found:
                errors.append(
                    f"Module '{manifest['id']}': dependency '{dep}' not found"
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
