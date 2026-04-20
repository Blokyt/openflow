"""Ensure no UI file references a module that has been removed from the codebase."""
import re
from pathlib import Path

# Modules removed in 2026-04-20 cleanup. Update this list every time a module is deleted.
REMOVED_MODULE_IDS = {
    "alerts",
    "multi_accounts",
    "divisions",
    "bank_reconciliation",
    "forecasting",
    "tax_receipts",
    "grants",
    "recurring",
}

# Fichiers qui ont le droit de mentionner ces ids (routes/registry).
EXEMPT_FILES = {
    "frontend/src/routes.tsx",
}

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "src"


def test_removed_module_ids_absent_from_frontend():
    """Aucun fichier UI ne doit plus citer un module supprimé."""
    hits = []
    # Build a regex with word boundaries for each removed id.
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(m) for m in REMOVED_MODULE_IDS) + r")\b"
    )

    for path in FRONTEND_DIR.rglob("*.ts*"):
        rel = path.relative_to(FRONTEND_DIR.parent.parent).as_posix()
        if rel in EXEMPT_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in pattern.finditer(text):
            # Skip lines with ignore marker
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line_text = text[line_start:line_end if line_end != -1 else len(text)]
            if "text-coherence-ignore" in line_text:
                continue
            # Compute line number for helpful error message
            line_no = text[: match.start()].count("\n") + 1
            hits.append(f"{rel}:{line_no} references removed module '{match.group(1)}'")

    assert not hits, (
        "Found references to removed modules:\n  " + "\n  ".join(hits)
        + "\nEither remove the reference, or if it's legitimate (e.g. routing), add the file to EXEMPT_FILES."
    )


def test_removed_module_manifests_absent_from_backend():
    """Double-check: no manifest.json remains for a removed module."""
    modules_dir = Path(__file__).parent.parent.parent / "backend" / "modules"
    existing = {p.name for p in modules_dir.iterdir() if p.is_dir()}
    overlap = existing & REMOVED_MODULE_IDS
    assert not overlap, f"Removed modules still have backend folders: {overlap}"
