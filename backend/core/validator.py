import json
from functools import lru_cache
from pathlib import Path
import jsonschema

SCHEMA_PATH = Path(__file__).parent.parent.parent / "tools" / "schemas" / "manifest.schema.json"


@lru_cache(maxsize=1)
def _get_validator() -> jsonschema.Draft202012Validator:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    return jsonschema.Draft202012Validator(schema)


def validate_manifest(manifest: dict) -> list[str]:
    return [e.message for e in _get_validator().iter_errors(manifest)]

def validate_manifest_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    return validate_manifest(manifest)

def check_module_files(manifest: dict, module_dir: str) -> list[str]:
    errors = []
    base = Path(module_dir)
    for route_file in manifest.get("api_routes", []):
        if not (base / route_file).exists():
            errors.append(f"Declared api_route not found: {route_file}")
    for model_file in manifest.get("db_models", []):
        if not (base / model_file).exists():
            errors.append(f"Declared db_model not found: {model_file}")
    return errors
