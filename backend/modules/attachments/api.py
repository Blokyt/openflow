"""Attachments API module for OpenFlow."""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from backend.core.database import get_conn

router = APIRouter()

ATTACHMENTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "attachments"


def ensure_attachments_dir():
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


@router.get("/transaction/{tx_id}")
def list_attachments(tx_id: int):
    conn = get_conn()
    try:
        tx = conn.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
        cur = conn.execute(
            "SELECT * FROM attachments WHERE transaction_id = ? ORDER BY created_at ASC",
            (tx_id,),
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/transaction/{tx_id}", status_code=201)
async def upload_attachment(tx_id: int, file: UploadFile = File(...)):
    ensure_attachments_dir()
    conn = get_conn()
    try:
        tx = conn.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")

        original_name = file.filename or "upload"
        unique_filename = f"{uuid.uuid4()}_{original_name}"
        file_path = ATTACHMENTS_DIR / unique_filename

        content = await file.read()
        file_path.write_bytes(content)

        mime_type = file.content_type or ""
        size = len(content)
        now = datetime.now(timezone.utc).isoformat()

        cur = conn.execute(
            "INSERT INTO attachments (transaction_id, filename, original_name, mime_type, size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tx_id, unique_filename, original_name, mime_type, size, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/{id}/download")
def download_attachment(id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Attachment {id} not found")
        attachment = row_to_dict(row)
    finally:
        conn.close()

    file_path = ATTACHMENTS_DIR / attachment["filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=attachment["original_name"],
        media_type=attachment["mime_type"] or "application/octet-stream",
    )


@router.delete("/{id}")
def delete_attachment(id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Attachment {id} not found")
        attachment = row_to_dict(row)

        conn.execute("DELETE FROM attachments WHERE id = ?", (id,))
        conn.commit()
    finally:
        conn.close()

    file_path = ATTACHMENTS_DIR / attachment["filename"]
    if file_path.exists():
        file_path.unlink()

    return {"deleted": id}
