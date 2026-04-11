import json
from pathlib import Path

def discover_modules(modules_dir: str) -> list[dict]:
    modules = []
    base = Path(modules_dir)
    if not base.exists():
        return modules
    for child in sorted(base.iterdir()):
        manifest_path = child / "manifest.json"
        if child.is_dir() and manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            modules.append(manifest)
    return modules

def filter_active(modules: list[dict], active_config: dict[str, bool]) -> list[dict]:
    return [m for m in modules if active_config.get(m["id"], False)]

def check_dependencies(active_manifests: list[dict]) -> list[str]:
    active_ids = {m["id"] for m in active_manifests}
    errors = []
    for manifest in active_manifests:
        for dep in manifest.get("dependencies", []):
            if dep not in active_ids:
                errors.append(f"Module '{manifest['id']}' requires '{dep}' but it is not active")
    return errors

def detect_route_conflicts(active_manifests: list[dict]) -> list[str]:
    prefixes = {}
    conflicts = []
    for manifest in active_manifests:
        prefix = f"/api/{manifest['id']}"
        if prefix in prefixes:
            conflicts.append(f"Route prefix conflict: '{prefix}' used by both '{prefixes[prefix]}' and '{manifest['id']}'")
        prefixes[prefix] = manifest["id"]
    return conflicts
