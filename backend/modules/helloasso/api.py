from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict
from backend.modules.helloasso.client import HelloAssoClient, HelloAssoError

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _with_pending(d: dict) -> dict:
    """Ajoute pending_cents = collecté - pointé (montant restant à prendre en compte)."""
    d["pending_cents"] = (d.get("collected_cents") or 0) - (d.get("acknowledged_cents") or 0)
    return d


# ---------------------------------------------------------------------------
# Configuration (clé API)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Synchronisation (lecture seule de l'API HelloAsso)
# ---------------------------------------------------------------------------

def _fiscal_year_bounds(conn, fiscal_year_id: int):
    row = conn.execute(
        "SELECT start_date, end_date FROM fiscal_years WHERE id = ?", (fiscal_year_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    start = row["start_date"] if hasattr(row, "keys") else row[0]
    end = row["end_date"] if hasattr(row, "keys") else row[1]
    return start, (end or "9999-12-31")


def _build_client(conn) -> HelloAssoClient:
    row = _load_config_row(conn)
    if row is None:
        raise HTTPException(status_code=400, detail="Clé API HelloAsso non configurée")
    data = row_to_dict(row)
    if not (data["client_id"] and data["client_secret"] and data["organization_slug"]):
        raise HTTPException(status_code=400, detail="Clé API HelloAsso incomplète")
    return HelloAssoClient(data["client_id"], data["client_secret"], data["organization_slug"])


@router.post("/sync")
def sync(fiscal_year_id: int):
    conn = get_conn()
    try:
        start, end = _fiscal_year_bounds(conn, fiscal_year_id)
        client = _build_client(conn)
        try:
            totals = client.fetch_campaign_totals(start, end)
        except HelloAssoError as e:
            raise HTTPException(status_code=502, detail=str(e))
        now = _now()
        for t in totals:
            # ON CONFLICT ne touche PAS acknowledged_cents : le pointage est préservé
            # d'une synchro à l'autre. C'est ce qui fait réapparaître une campagne
            # « à traiter » quand le collecté augmente au-delà du montant déjà pointé.
            conn.execute(
                """INSERT INTO helloasso_campaigns
                   (fiscal_year_id, form_type, form_slug, title, state, collected_cents, currency, last_synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(fiscal_year_id, form_type, form_slug) DO UPDATE SET
                       title = excluded.title,
                       state = excluded.state,
                       collected_cents = excluded.collected_cents,
                       currency = excluded.currency,
                       last_synced_at = excluded.last_synced_at""",
                (fiscal_year_id, t["form_type"], t["form_slug"], t["title"], t["state"],
                 t["collected_cents"], t["currency"], now),
            )
        conn.commit()
        cached = conn.execute(
            "SELECT * FROM helloasso_campaigns WHERE fiscal_year_id = ? ORDER BY title", (fiscal_year_id,)
        ).fetchall()
        return [_with_pending(row_to_dict(r)) for r in cached]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lecture + pointage manuel (acquittement)
# ---------------------------------------------------------------------------

@router.get("/campaigns")
def list_campaigns(fiscal_year_id: int):
    conn = get_conn()
    try:
        campaigns = conn.execute(
            "SELECT * FROM helloasso_campaigns WHERE fiscal_year_id = ? ORDER BY title",
            (fiscal_year_id,),
        ).fetchall()
        return [_with_pending(row_to_dict(c)) for c in campaigns]
    finally:
        conn.close()


class AcknowledgePayload(BaseModel):
    form_type: str
    form_slug: str
    fiscal_year_id: int


def _get_campaign(conn, p: AcknowledgePayload) -> dict:
    row = conn.execute(
        "SELECT * FROM helloasso_campaigns WHERE fiscal_year_id = ? AND form_type = ? AND form_slug = ?",
        (p.fiscal_year_id, p.form_type, p.form_slug),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Campagne introuvable : lance d'abord une synchronisation")
    return row_to_dict(row)


@router.post("/acknowledge")
def acknowledge(payload: AcknowledgePayload):
    """Marque la campagne comme prise en compte : on pointe le montant collecté
    actuel. La campagne ne réapparaîtra comme « à traiter » que si HelloAsso
    encaisse davantage par la suite."""
    conn = get_conn()
    try:
        camp = _get_campaign(conn, payload)
        conn.execute(
            "UPDATE helloasso_campaigns SET acknowledged_cents = ? WHERE id = ?",
            (camp["collected_cents"], camp["id"]),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM helloasso_campaigns WHERE id = ?", (camp["id"],)).fetchone()
        return _with_pending(row_to_dict(row))
    finally:
        conn.close()


@router.post("/unacknowledge")
def unacknowledge(payload: AcknowledgePayload):
    """Annule le pointage : la campagne réapparaît avec tout son collecté à traiter."""
    conn = get_conn()
    try:
        camp = _get_campaign(conn, payload)
        conn.execute(
            "UPDATE helloasso_campaigns SET acknowledged_cents = 0 WHERE id = ?",
            (camp["id"],),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM helloasso_campaigns WHERE id = ?", (camp["id"],)).fetchone()
        return _with_pending(row_to_dict(row))
    finally:
        conn.close()
