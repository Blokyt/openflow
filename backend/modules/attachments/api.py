"""Attachments API module for OpenFlow."""
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse

from backend.core.auth import get_allowed_entity_ids, get_current_user
from backend.core.database import get_conn, row_to_dict
from backend.core.uploads import require_allowed_upload

router = APIRouter()

ATTACHMENTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "attachments"

# Taille maximale d'un justificatif (20 Mo). Au-delà : 413.
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024


def _sanitize_filename(name: str) -> str:
    """Réduit un nom de fichier client à un basename sûr, sans séquence de
    traversal (`..`, `/`, `\\`) ni caractère de contrôle. Renvoie "upload"
    si rien d'exploitable ne reste."""
    base = Path(name or "").name
    base = base.replace("\\", "/").split("/")[-1]   # dernier segment, cross-OS
    base = re.sub(r"[^\w.\-]", "_", base)            # caractères sûrs uniquement
    base = re.sub(r"\.{2,}", "_", base)              # neutralise les séquences ".."
    base = base.strip("._ ")                         # bords sans points/underscores/espaces
    return base[:128] or "upload"


def ensure_attachments_dir():
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _require_tx_access(conn, request: Request, tx_id: int) -> None:
    user = get_current_user(request)
    allowed = get_allowed_entity_ids(conn, user)
    if allowed is None:
        return
    tx = conn.execute(
        "SELECT from_entity_id, to_entity_id FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    if tx is None or (tx["from_entity_id"] not in allowed and tx["to_entity_id"] not in allowed):
        raise HTTPException(status_code=403, detail="Accès refusé à cette pièce jointe")


def _require_submission_access(conn, request: Request, submission_id: int) -> None:
    """Accès à une soumission : son auteur ou l'admin."""
    user = get_current_user(request)
    if user["is_admin"]:
        return
    sub = conn.execute(
        "SELECT submitted_by FROM transaction_submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    if sub is None or sub["submitted_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Accès refusé à cette pièce jointe")


def _require_attachment_access(conn, request: Request, attachment: dict) -> None:
    """Une pièce liée à une transaction suit le périmètre de la transaction ;
    une pièce liée seulement à une soumission suit l'auteur de la soumission."""
    if attachment["transaction_id"] is not None:
        _require_tx_access(conn, request, attachment["transaction_id"])
        return
    if attachment.get("submission_id") is not None:
        _require_submission_access(conn, request, attachment["submission_id"])
        return
    # Pièce orpheline : admin uniquement.
    user = get_current_user(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé à cette pièce jointe")


@router.get("/transaction/{tx_id}")
def list_attachments(tx_id: int, request: Request):
    conn = get_conn()
    try:
        tx = conn.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
        _require_tx_access(conn, request, tx_id)
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

        # Limite de taille : on lit au plus MAX+1 octets pour détecter le dépassement.
        content = await file.read(MAX_ATTACHMENT_SIZE + 1)
        if len(content) > MAX_ATTACHMENT_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux (max {MAX_ATTACHMENT_SIZE // (1024 * 1024)} Mo)",
            )

        # Liste blanche par magic bytes : le MIME stocké est celui détecté.
        detected_mime = require_allowed_upload(content)

        # Assainissement du nom de fichier (anti path traversal).
        original_name = _sanitize_filename(file.filename or "upload")
        unique_filename = f"{uuid.uuid4()}_{original_name}"
        file_path = ATTACHMENTS_DIR / unique_filename
        # Défense en profondeur : le chemin résolu doit rester dans ATTACHMENTS_DIR.
        if not file_path.resolve().is_relative_to(ATTACHMENTS_DIR.resolve()):
            raise HTTPException(status_code=400, detail="Nom de fichier invalide")

        file_path.write_bytes(content)

        mime_type = detected_mime
        size = len(content)
        now = datetime.now(timezone.utc).isoformat()

        cur = conn.execute(
            "INSERT INTO attachments (transaction_id, filename, original_name, mime_type, size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tx_id, unique_filename, original_name, mime_type, size, now),
        )
        attach_id = cur.lastrowid
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attach_id,)).fetchone()
        attach_data = row_to_dict(row)
        conn.commit()
        return attach_data
    finally:
        conn.close()


@router.get("/submission/{submission_id}")
def list_submission_attachments(submission_id: int, request: Request):
    conn = get_conn()
    try:
        sub = conn.execute(
            "SELECT id FROM transaction_submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if sub is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        _require_submission_access(conn, request, submission_id)
        cur = conn.execute(
            "SELECT * FROM attachments WHERE submission_id = ? ORDER BY created_at ASC",
            (submission_id,),
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/submission/{submission_id}", status_code=201)
async def upload_submission_attachment(submission_id: int, request: Request, file: UploadFile = File(...)):
    ensure_attachments_dir()
    conn = get_conn()
    try:
        sub = conn.execute(
            "SELECT submitted_by, status FROM transaction_submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if sub is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        user = get_current_user(request)
        if not user["is_admin"] and sub["submitted_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="Seul l'auteur peut joindre un justificatif")
        if sub["status"] != "pending":
            raise HTTPException(status_code=409, detail="La soumission n'est plus en attente")

        content = await file.read(MAX_ATTACHMENT_SIZE + 1)
        if len(content) > MAX_ATTACHMENT_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux (max {MAX_ATTACHMENT_SIZE // (1024 * 1024)} Mo)",
            )

        # Liste blanche par magic bytes : le MIME stocké est celui détecté.
        detected_mime = require_allowed_upload(content)

        original_name = _sanitize_filename(file.filename or "upload")
        unique_filename = f"{uuid.uuid4()}_{original_name}"
        file_path = ATTACHMENTS_DIR / unique_filename
        if not file_path.resolve().is_relative_to(ATTACHMENTS_DIR.resolve()):
            raise HTTPException(status_code=400, detail="Nom de fichier invalide")
        file_path.write_bytes(content)

        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO attachments (transaction_id, submission_id, filename, original_name, mime_type, size, created_at) "
            "VALUES (NULL, ?, ?, ?, ?, ?, ?)",
            (submission_id, unique_filename, original_name, detected_mime, len(content), now),
        )
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (cur.lastrowid,)).fetchone()
        data = row_to_dict(row)
        conn.commit()
        return data
    finally:
        conn.close()


@router.get("/{id}/preview")
def preview_attachment(id: int, request: Request):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Attachment {id} not found")
        attachment = row_to_dict(row)
        _require_attachment_access(conn, request, attachment)
    finally:
        conn.close()

    file_path = ATTACHMENTS_DIR / attachment["filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Renvoie le fichier en inline (pas de Content-Disposition: attachment)
    # afin qu'il s'affiche directement dans le navigateur.
    return FileResponse(
        path=str(file_path),
        media_type=attachment["mime_type"] or "application/octet-stream",
    )


@router.get("/{id}/download")
def download_attachment(id: int, request: Request):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Attachment {id} not found")
        attachment = row_to_dict(row)
        _require_attachment_access(conn, request, attachment)
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
def delete_attachment(id: int, request: Request):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Attachment {id} not found")
        attachment = row_to_dict(row)

        user = get_current_user(request)
        if not user["is_admin"]:
            # Un non-admin ne supprime que les pièces de SA soumission encore pending.
            allowed = False
            if attachment["transaction_id"] is None and attachment["submission_id"] is not None:
                sub = conn.execute(
                    "SELECT submitted_by, status FROM transaction_submissions WHERE id = ?",
                    (attachment["submission_id"],),
                ).fetchone()
                allowed = (
                    sub is not None
                    and sub["submitted_by"] == user["id"]
                    and sub["status"] == "pending"
                )
            if not allowed:
                raise HTTPException(status_code=403, detail="Suppression réservée à l'administrateur")

        conn.execute("DELETE FROM attachments WHERE id = ?", (id,))
        conn.commit()
    finally:
        conn.close()

    file_path = ATTACHMENTS_DIR / attachment["filename"]
    if file_path.exists():
        file_path.unlink()

    return {"deleted": id}
