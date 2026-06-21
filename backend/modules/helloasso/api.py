from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConfigPayload(BaseModel):
    client_id: str
    client_secret: str
    organization_slug: str


def _load_config_row(conn):
    return conn.execute("SELECT * FROM helloasso_config WHERE id = 1").fetchone()


@router.get("/config")
def get_config():
    conn = get_conn()
    try:
        row = _load_config_row(conn)
        if row is None:
            return {"configured": False, "organization_slug": "", "has_secret": False}
        data = row_to_dict(row)
        configured = bool(data["client_id"] and data["client_secret"] and data["organization_slug"])
        return {
            "configured": configured,
            "organization_slug": data["organization_slug"],
            "has_secret": bool(data["client_secret"]),
        }
    finally:
        conn.close()


@router.put("/config")
def put_config(payload: ConfigPayload):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO helloasso_config (id, client_id, client_secret, organization_slug, updated_at)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   client_id = excluded.client_id,
                   client_secret = excluded.client_secret,
                   organization_slug = excluded.organization_slug,
                   updated_at = excluded.updated_at""",
            (payload.client_id, payload.client_secret, payload.organization_slug, _now()),
        )
        conn.commit()
        return {"configured": bool(payload.client_id and payload.client_secret and payload.organization_slug)}
    finally:
        conn.close()
