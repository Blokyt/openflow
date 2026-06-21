from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict
from backend.modules.helloasso.client import HelloAssoClient, HelloAssoError

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
        return [row_to_dict(r) for r in cached]
    finally:
        conn.close()


class LinkPayload(BaseModel):
    form_type: str
    form_slug: str
    category_id: int | None = None
    from_entity_id: int
    to_entity_id: int


@router.get("/links")
def list_links():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM helloasso_links ORDER BY id").fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.put("/links")
def upsert_link(payload: LinkPayload):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO helloasso_links
               (form_type, form_slug, category_id, from_entity_id, to_entity_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(form_type, form_slug) DO UPDATE SET
                   category_id = excluded.category_id,
                   from_entity_id = excluded.from_entity_id,
                   to_entity_id = excluded.to_entity_id""",
            (payload.form_type, payload.form_slug, payload.category_id,
             payload.from_entity_id, payload.to_entity_id, _now()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM helloasso_links WHERE form_type = ? AND form_slug = ?",
            (payload.form_type, payload.form_slug),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def _recorded_cents(conn, category_id, club_entity_id, start, end) -> int:
    """Net pour le club sur la categorie, dans la periode (entrants - sortants)."""
    row = conn.execute(
        """SELECT COALESCE(SUM(CASE
                WHEN to_entity_id = ? THEN amount
                WHEN from_entity_id = ? THEN -amount
                ELSE 0 END), 0)
           FROM transactions
           WHERE date BETWEEN ? AND ?
             AND category_id IS ?
             AND (from_entity_id = ? OR to_entity_id = ?)""",
        (club_entity_id, club_entity_id, start, end, category_id, club_entity_id, club_entity_id),
    ).fetchone()
    return row[0] if not hasattr(row, "keys") else row[0]


class AdjustPayload(BaseModel):
    form_type: str
    form_slug: str
    fiscal_year_id: int


@router.post("/adjust", status_code=201)
def adjust(payload: AdjustPayload):
    conn = get_conn()
    try:
        start, end = _fiscal_year_bounds(conn, payload.fiscal_year_id)
        campaign = conn.execute(
            "SELECT * FROM helloasso_campaigns WHERE fiscal_year_id = ? AND form_type = ? AND form_slug = ?",
            (payload.fiscal_year_id, payload.form_type, payload.form_slug),
        ).fetchone()
        if campaign is None:
            raise HTTPException(status_code=400, detail="Campagne absente du cache : lance d'abord une synchro")
        link = conn.execute(
            "SELECT * FROM helloasso_links WHERE form_type = ? AND form_slug = ?",
            (payload.form_type, payload.form_slug),
        ).fetchone()
        if link is None:
            raise HTTPException(status_code=400, detail="Campagne non rattachée à un poste de la compta")

        camp = row_to_dict(campaign)
        lk = row_to_dict(link)
        recorded = _recorded_cents(conn, lk["category_id"], lk["to_entity_id"], start, end)
        gap = camp["collected_cents"] - recorded
        if gap == 0:
            raise HTTPException(status_code=400, detail="Aucun écart à ajuster")

        amount = abs(gap)
        if gap > 0:  # collecté > enregistré : recette qui entre dans le club
            from_id, to_id = lk["from_entity_id"], lk["to_entity_id"]
        else:        # enregistré > collecté : régularisation, sortie du club
            from_id, to_id = lk["to_entity_id"], lk["from_entity_id"]

        today = datetime.now(timezone.utc).date().isoformat()
        now = _now()
        label = f"Ajustement HelloAsso, {camp['title']}"
        cur = conn.execute(
            """INSERT INTO transactions
               (date, label, description, amount, category_id, contact_id, created_by, from_entity_id, to_entity_id, created_at, updated_at)
               VALUES (?, ?, '', ?, ?, NULL, 'helloasso', ?, ?, ?, ?)""",
            (today, label, amount, lk["category_id"], from_id, to_id, now, now),
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (new_id,)).fetchone()
        conn.commit()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/campaigns")
def list_campaigns(fiscal_year_id: int):
    conn = get_conn()
    try:
        start, end = _fiscal_year_bounds(conn, fiscal_year_id)
        campaigns = conn.execute(
            "SELECT * FROM helloasso_campaigns WHERE fiscal_year_id = ? ORDER BY title",
            (fiscal_year_id,),
        ).fetchall()
        links = {}
        for r in conn.execute("SELECT * FROM helloasso_links").fetchall():
            d = row_to_dict(r)
            links[(d["form_type"], d["form_slug"])] = d
        out = []
        for c in campaigns:
            data = row_to_dict(c)
            link = links.get((data["form_type"], data["form_slug"]))
            if link is None:
                data["link"] = None
                data["recorded_cents"] = None
                data["gap_cents"] = None
            else:
                recorded = _recorded_cents(conn, link["category_id"], link["to_entity_id"], start, end)
                data["link"] = link
                data["recorded_cents"] = recorded
                data["gap_cents"] = data["collected_cents"] - recorded
            out.append(data)
        return out
    finally:
        conn.close()
