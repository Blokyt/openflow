import json
from pathlib import Path
import jsonschema

SCHEMA_PATH = Path(__file__).parent.parent.parent / "tools" / "schemas" / "manifest.schema.json"

def _load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)

def validate_manifest(manifest: dict) -> list[str]:
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(manifest)]

def validate_manifest_file(path: str) -> list[str]:
    with open(path) as f:
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
