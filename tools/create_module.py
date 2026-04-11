#!/usr/bin/env python3
"""Scaffold a new OpenFlow module."""
import argparse
import json
import sys
from pathlib import Path

MANIFEST_TEMPLATE = {
    "id": "",
    "name": "",
    "description": "",
    "version": "1.0.0",
    "origin": "custom",
    "category": "custom",
    "dependencies": [],
    "menu": {"label": "", "icon": "box", "position": 99},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}

API_TEMPLATE = (
    '"""API routes for {name} module."""\n'
    "from fastapi import APIRouter\n\n"
    "router = APIRouter()\n\n"
    "@router.get(\"/\")\n"
    "def list_{id}():\n"
    "    return []\n"
)

MODELS_TEMPLATE = (
    '"""Database models for {name} module."""\n\n'
    "migrations = {{\n"
    '    "1.0.0": [],\n'
    "}}\n"
)

INDEX_TSX_TEMPLATE = (
    'import React from "react";\n\n'
    "export default function {component_name}() {{\n"
    '  return (\n'
    '    <div className="p-6">\n'
    '      <h1 className="text-2xl font-bold">{name}</h1>\n'
    '      <p className="text-gray-600 mt-2">{description}</p>\n'
    "    </div>\n"
    "  );\n"
    "}}\n"
)


def main():
    parser = argparse.ArgumentParser(description="Create a new OpenFlow module")
    parser.add_argument("module_id")
    parser.add_argument("--project-dir", default=str(Path(__file__).parent.parent))
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument(
        "--category",
        default="custom",
        choices=["core", "standard", "advanced", "custom"],
    )
    parser.add_argument(
        "--origin", default="custom", choices=["builtin", "custom"]
    )
    args = parser.parse_args()

    project = Path(args.project_dir)
    backend_dir = project / "backend" / "modules" / args.module_id
    frontend_dir = project / "frontend" / "src" / "modules" / args.module_id

    if backend_dir.exists():
        print(
            f"Error: module '{args.module_id}' already exists at {backend_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Create backend files
    backend_dir.mkdir(parents=True)
    manifest = {
        **MANIFEST_TEMPLATE,
        "id": args.module_id,
        "name": args.name,
        "description": args.description,
        "category": args.category,
        "origin": args.origin,
    }
    manifest["menu"] = {**manifest["menu"], "label": args.name}

    with open(backend_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    with open(backend_dir / "api.py", "w") as f:
        f.write(API_TEMPLATE.format(name=args.name, id=args.module_id))

    with open(backend_dir / "models.py", "w") as f:
        f.write(MODELS_TEMPLATE.format(name=args.name))

    # Create frontend files
    frontend_dir.mkdir(parents=True)
    (frontend_dir / "components").mkdir()
    (frontend_dir / "widgets").mkdir()

    component_name = "".join(word.capitalize() for word in args.module_id.split("_"))

    with open(frontend_dir / "index.tsx", "w") as f:
        f.write(
            INDEX_TSX_TEMPLATE.format(
                component_name=component_name,
                name=args.name,
                description=args.description,
            )
        )

    print(f"Module '{args.module_id}' created successfully:")
    print(f"  Backend:  {backend_dir}")
    print(f"  Frontend: {frontend_dir}")


if __name__ == "__main__":
    main()
