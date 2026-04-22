"""Smart Import API.

Endpoints:
  POST /analyze       Upload a file, run all parsers, return their results with diff previews.
  POST /commit        Apply a parse result (commit new + update modified transactions).
  GET  /parsers       List available parsers.
"""
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.core.database import get_conn, get_db_path
from backend.modules.smart_import.diff import compute_diff
from backend.modules.smart_import.parsers import get_all_parsers

router = APIRouter()

# Temp directory for uploaded files, keyed by import_id
TEMP_DIR = Path(get_db_path()).parent / "smart_import_temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

_STALE_THRESHOLD_SECONDS = 3600  # 1 hour


def cleanup_stale_temps(temp_dir: Optional[Path] = None) -> None:
    """Delete any file in *temp_dir* (defaults to TEMP_DIR) older than 1 hour.

    Called opportunistically at the top of each endpoint that touches the temp
    directory — no scheduler required.
    """
    target = temp_dir if temp_dir is not None else TEMP_DIR
    if not target.exists():
        return
    cutoff = time.time() - _STALE_THRESHOLD_SECONDS
    for f in target.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
            except Exception:
                pass


@router.get("/parsers")
def list_parsers():
    """List all registered parsers."""
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "supported_extensions": p.supported_extensions,
        }
        for p in get_all_parsers()
    ]


@router.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    """Upload a file and return parsing attempts from all applicable parsers."""
    cleanup_stale_temps()
    if not file.filename:
        raise HTTPException(400, "Nom de fichier manquant")

    ext = Path(file.filename).suffix.lower()
    import_id = str(uuid.uuid4())
    temp_path = TEMP_DIR / f"{import_id}{ext}"

    # Save uploaded file
    content = await file.read()
    with open(temp_path, "wb") as f:
        f.write(content)

    parsers = get_all_parsers()

    # Run detection on each parser
    candidates = []
    for p in parsers:
        try:
            confidence = p.detect(str(temp_path), ext)
        except Exception as e:
            confidence = 0.0
        if confidence > 0.0:
            candidates.append((p, confidence))

    candidates.sort(key=lambda x: -x[1])

    # Run parse on applicable candidates
    results = []
    conn = get_conn()
    try:
        for p, confidence in candidates:
            try:
                parse_result = p.parse(str(temp_path))
                parse_result.confidence = confidence
            except Exception as e:
                results.append({
                    "parser_id": p.id,
                    "parser_name": p.name,
                    "confidence": confidence,
                    "error": f"Parse failed: {e}",
                    "transactions": [],
                    "diff": {"stats": {"new": 0, "modified": 0, "unchanged": 0, "total": 0}, "items": []},
                })
                continue

            # Compute diff against DB
            diff = compute_diff(conn, parse_result.transactions)

            results.append({
                "parser_id": parse_result.parser_id,
                "parser_name": parse_result.parser_name,
                "confidence": confidence,
                "transactions_count": len(parse_result.transactions),
                "errors": parse_result.errors,
                "warnings": parse_result.warnings[:10],  # cap
                "meta": parse_result.meta,
                "diff": diff,
            })
    finally:
        conn.close()

    return {
        "import_id": import_id,
        "filename": file.filename,
        "extension": ext,
        "results": results,
    }


class CommitRequest(BaseModel):
    import_id: str
    parser_id: str
    apply_new: bool = True
    apply_modifications: bool = True


@router.post("/commit")
def commit(req: CommitRequest):
    """Apply the chosen parser's result: insert new + update modified transactions."""
    cleanup_stale_temps()
    # Find the temp file for this import_id
    matches = list(TEMP_DIR.glob(f"{req.import_id}.*"))
    if not matches:
        raise HTTPException(404, f"Import session {req.import_id} introuvable ou expir\u00e9e")
    temp_path = matches[0]

    # Find the parser
    parsers = {p.id: p for p in get_all_parsers()}
    parser = parsers.get(req.parser_id)
    if not parser:
        raise HTTPException(404, f"Parser '{req.parser_id}' introuvable")

    # Re-parse (idempotent)
    try:
        parse_result = parser.parse(str(temp_path))
    except Exception as e:
        raise HTTPException(500, f"Erreur de parsing: {e}")

    conn = get_conn()
    created = 0
    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    try:
        # Find root entity for default from/to
        root = conn.execute(
            "SELECT id FROM entities WHERE is_default = 1 AND parent_id IS NULL"
        ).fetchone()
        default_entity = root["id"] if root else None

        # Find external entity 'Divers Externe' or any external for counterparty
        ext_entity = conn.execute(
            "SELECT id FROM entities WHERE type = 'external' AND is_divers = 1 LIMIT 1"
        ).fetchone()
        if not ext_entity:
            ext_entity = conn.execute(
                "SELECT id FROM entities WHERE type = 'external' LIMIT 1"
            ).fetchone()
        default_external = ext_entity["id"] if ext_entity else default_entity

        diff = compute_diff(conn, parse_result.transactions)

        for item in diff["items"]:
            draft = item["draft"]

            if item["status"] == "unchanged":
                skipped += 1
                continue

            if item["status"] == "new" and req.apply_new:
                # Determine from/to based on sign
                if draft["amount"] < 0:
                    from_id, to_id = default_entity, default_external
                else:
                    from_id, to_id = default_external, default_entity

                cur = conn.execute(
                    """INSERT INTO transactions (date, label, description, amount,
                       from_entity_id, to_entity_id, created_by, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'smart_import', ?, ?)""",
                    (draft["date"], draft["label"], draft.get("description", ""),
                     draft["amount"], from_id, to_id, now, now),
                )
                tx_id = cur.lastrowid
                created += 1

                reimb = draft.get("reimbursement")
                if reimb and reimb.get("person_name"):
                    status = reimb.get("status", "pending")
                    reimbursed_date = draft["date"] if status == "reimbursed" else None
                    conn.execute(
                        """INSERT INTO reimbursements
                           (transaction_id, person_name, amount, status, reimbursed_date, notes, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, '', ?, ?)""",
                        (tx_id, reimb["person_name"], abs(draft["amount"]), status, reimbursed_date, now, now),
                    )

            elif item["status"] == "modified" and req.apply_modifications:
                existing_id = item["existing"]["id"]
                conn.execute(
                    "UPDATE transactions SET amount = ?, updated_at = ? WHERE id = ?",
                    (draft["amount"], now, existing_id),
                )
                updated += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Erreur lors de l'application: {e}")
    finally:
        conn.close()

    # Clean up temp file
    try:
        temp_path.unlink()
    except Exception:
        pass

    return {
        "success": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


@router.delete("/cancel/{import_id}")
def cancel(import_id: str):
    """Clean up temp file for an abandoned import."""
    matches = list(TEMP_DIR.glob(f"{import_id}.*"))
    for m in matches:
        try:
            m.unlink()
        except Exception:
            pass
    return {"cancelled": import_id, "files_removed": len(matches)}
