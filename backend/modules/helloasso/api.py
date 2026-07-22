import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.core.auth import require_admin
from backend.core.database import get_conn, row_to_dict
from backend.modules.helloasso.client import HelloAssoClient, HelloAssoError

router = APIRouter(dependencies=[Depends(require_admin)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Calcul du lié / restant
# ---------------------------------------------------------------------------

def _linked_cents_map(conn, campaign_ids) -> dict:
    """Retourne {campaign_id: linked_cents}.

    linked_cents = somme des montants des transactions liées à la campagne. Le
    JOIN avec transactions ignore les liens orphelins (transaction supprimée),
    ce qui évite tout couplage avec le module transactions (pas de cascade).
    """
    ids = [c for c in campaign_ids]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT l.campaign_id AS cid,
                   COALESCE(SUM(COALESCE(l.amount_cents, t.amount)), 0) AS linked
            FROM helloasso_campaign_transactions l
            JOIN transactions t ON t.id = l.transaction_id
            WHERE l.campaign_id IN ({ph})
            GROUP BY l.campaign_id""",
        ids,
    ).fetchall()
    return {r["cid"]: r["linked"] for r in rows}


def _enrich(d: dict, linked: int) -> dict:
    """Ajoute linked_cents et pending_cents (collecté - lié) à une campagne."""
    d["linked_cents"] = linked
    d["pending_cents"] = (d.get("collected_cents") or 0) - linked
    return d


def _enrich_all(conn, rows) -> list:
    """Enrichit une liste de lignes campagnes avec linked_cents/pending_cents."""
    campaigns = [row_to_dict(r) for r in rows]
    linked = _linked_cents_map(conn, [c["id"] for c in campaigns])
    return [_enrich(c, linked.get(c["id"], 0)) for c in campaigns]


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
            # ON CONFLICT préserve l'id de la campagne : les associations de
            # transactions (qui référencent campaign_id) survivent au re-sync.
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
        return _enrich_all(conn, cached)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lecture des campagnes
# ---------------------------------------------------------------------------

@router.get("/campaigns")
def list_campaigns(fiscal_year_id: int):
    conn = get_conn()
    try:
        try:
            if conn.execute("SELECT 1 FROM fiscal_years WHERE id = ?", (fiscal_year_id,)).fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Exercice fiscal {fiscal_year_id} introuvable")
        except sqlite3.OperationalError:
            pass  # module budget absent : pas de validation possible
        campaigns = conn.execute(
            "SELECT * FROM helloasso_campaigns WHERE fiscal_year_id = ? ORDER BY title",
            (fiscal_year_id,),
        ).fetchall()
        return _enrich_all(conn, campaigns)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Association de transactions à une campagne
# ---------------------------------------------------------------------------

def _get_campaign_by_id(conn, campaign_id: int) -> dict:
    row = conn.execute("SELECT * FROM helloasso_campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Campagne introuvable : lance d'abord une synchronisation")
    return row_to_dict(row)


def _links_payload(conn, campaign_id: int, camp: dict) -> dict:
    """Construit la réponse {campagne, transactions liées, lié, restant}."""
    rows = conn.execute(
        """SELECT l.id AS link_id, t.id AS transaction_id, t.date, t.label,
                  COALESCE(l.amount_cents, t.amount) AS amount, t.amount AS tx_amount,
                  t.from_entity_id, t.to_entity_id,
                  fe.name AS from_entity_name, te.name AS to_entity_name
           FROM helloasso_campaign_transactions l
           JOIN transactions t ON t.id = l.transaction_id
           LEFT JOIN entities fe ON fe.id = t.from_entity_id
           LEFT JOIN entities te ON te.id = t.to_entity_id
           WHERE l.campaign_id = ?
           ORDER BY t.date, t.id""",
        (campaign_id,),
    ).fetchall()
    links = [row_to_dict(r) for r in rows]
    linked = sum(l["amount"] for l in links)
    return {
        "campaign_id": campaign_id,
        "collected_cents": camp["collected_cents"],
        "linked_cents": linked,
        "pending_cents": camp["collected_cents"] - linked,
        "links": links,
    }


class LinkPayload(BaseModel):
    transaction_id: int
    # Montant imputé à cette campagne (centimes). Absent = imputation auto
    # (min du restant de la campagne et du restant non imputé de la transaction).
    amount_cents: int | None = None


def _tx_allocated(conn, transaction_id: int) -> int:
    """Montant déjà imputé de cette transaction, toutes campagnes confondues."""
    row = conn.execute(
        """SELECT COALESCE(SUM(COALESCE(l.amount_cents, t.amount)), 0) AS alloc
           FROM helloasso_campaign_transactions l
           JOIN transactions t ON t.id = l.transaction_id
           WHERE l.transaction_id = ?""",
        (transaction_id,),
    ).fetchone()
    return row["alloc"] if row else 0


@router.get("/campaigns/{campaign_id}/links")
def list_campaign_links(campaign_id: int):
    """Transactions associées à une campagne + montant lié et restant."""
    conn = get_conn()
    try:
        camp = _get_campaign_by_id(conn, campaign_id)
        return _links_payload(conn, campaign_id, camp)
    finally:
        conn.close()


@router.post("/campaigns/{campaign_id}/links", status_code=201)
def add_campaign_link(campaign_id: int, payload: LinkPayload):
    """Impute (une partie d')une transaction à la campagne. Many-to-many : une
    transaction peut être répartie sur plusieurs campagnes et une campagne
    couverte par plusieurs transactions (comme le rapprochement bancaire)."""
    conn = get_conn()
    try:
        camp = _get_campaign_by_id(conn, campaign_id)
        tx = conn.execute(
            "SELECT id, amount FROM transactions WHERE id = ?", (payload.transaction_id,)
        ).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail="Transaction introuvable")
        dup = conn.execute(
            "SELECT 1 FROM helloasso_campaign_transactions WHERE campaign_id = ? AND transaction_id = ?",
            (campaign_id, payload.transaction_id),
        ).fetchone()
        if dup is not None:
            raise HTTPException(status_code=409, detail="Cette transaction est déjà associée à cette campagne")

        tx_amount = tx["amount"] if hasattr(tx, "keys") else tx[1]
        tx_remaining = tx_amount - _tx_allocated(conn, payload.transaction_id)
        if tx_remaining <= 0:
            raise HTTPException(status_code=400, detail="Cette transaction est déjà entièrement imputée")
        campaign_pending = camp["collected_cents"] - _linked_cents_map(conn, [campaign_id]).get(campaign_id, 0)

        if payload.amount_cents is not None:
            amount = payload.amount_cents
            if amount <= 0:
                raise HTTPException(status_code=400, detail="Le montant imputé doit être positif")
            if amount > tx_remaining:
                raise HTTPException(status_code=400, detail="Montant supérieur au restant non imputé de la transaction")
        else:
            # Imputation auto : ce qui reste à couvrir sur la campagne, borné par
            # le restant de la transaction. Si la campagne est déjà couverte, on
            # impute quand même le restant de la transaction (l'écart s'affiche).
            base = campaign_pending if campaign_pending > 0 else tx_remaining
            amount = max(1, min(tx_remaining, base))

        try:
            conn.execute(
                "INSERT INTO helloasso_campaign_transactions (campaign_id, transaction_id, amount_cents, created_at) VALUES (?, ?, ?, ?)",
                (campaign_id, payload.transaction_id, amount, _now()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Cette transaction est déjà associée à cette campagne")
        conn.commit()
        return _links_payload(conn, campaign_id, camp)
    finally:
        conn.close()


@router.delete("/campaigns/{campaign_id}/links/{transaction_id}")
def remove_campaign_link(campaign_id: int, transaction_id: int):
    """Dissocie une transaction de la campagne."""
    conn = get_conn()
    try:
        camp = _get_campaign_by_id(conn, campaign_id)
        cur = conn.execute(
            "DELETE FROM helloasso_campaign_transactions WHERE campaign_id = ? AND transaction_id = ?",
            (campaign_id, transaction_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Association introuvable")
        conn.commit()
        return _links_payload(conn, campaign_id, camp)
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/suggestions")
def campaign_suggestions(campaign_id: int, limit: int = Query(default=20, ge=1, le=200)):
    """Propose les recettes du mandat (encaissements : entité externe -> interne)
    non encore liées à une campagne, triées « la plus proche inférieurement » du
    montant restant à couvrir."""
    conn = get_conn()
    try:
        camp = _get_campaign_by_id(conn, campaign_id)
        start, end = _fiscal_year_bounds(conn, camp["fiscal_year_id"])
        linked = _linked_cents_map(conn, [campaign_id]).get(campaign_id, 0)
        reste = camp["collected_cents"] - linked

        internal_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM entities WHERE type = 'internal'"
        ).fetchall()]
        suggestions = []
        if internal_ids:
            ph = ",".join("?" * len(internal_ids))
            # remaining_cents = montant de la transaction non encore imputé (à une
            # campagne quelconque). On propose ce restant, borné à ce qui manque
            # sur la campagne. Une transaction déjà partiellement imputée reste
            # proposée tant qu'il lui reste du montant (cas régularisation).
            rows = conn.execute(
                f"""SELECT t.id AS transaction_id, t.date, t.label, t.amount,
                           t.from_entity_id, t.to_entity_id,
                           fe.name AS from_entity_name, te.name AS to_entity_name,
                           t.amount - COALESCE(SUM(CASE WHEN l.id IS NOT NULL
                               THEN COALESCE(l.amount_cents, t.amount) ELSE 0 END), 0) AS remaining_cents
                    FROM transactions t
                    LEFT JOIN helloasso_campaign_transactions l ON l.transaction_id = t.id
                    LEFT JOIN entities fe ON fe.id = t.from_entity_id
                    LEFT JOIN entities te ON te.id = t.to_entity_id
                    WHERE t.date BETWEEN ? AND ?
                      AND t.to_entity_id IN ({ph})
                      AND (t.from_entity_id IS NULL OR t.from_entity_id NOT IN ({ph}))
                      AND t.id NOT IN (SELECT transaction_id FROM helloasso_campaign_transactions WHERE campaign_id = ?)
                    GROUP BY t.id
                    HAVING remaining_cents > 0
                    ORDER BY (remaining_cents > ?) ASC, ABS(remaining_cents - ?) ASC, t.date DESC
                    LIMIT ?""",
                [start, end] + internal_ids + internal_ids + [campaign_id, reste, reste, limit],
            ).fetchall()
            suggestions = [row_to_dict(r) for r in rows]

        return {
            "campaign_id": campaign_id,
            "collected_cents": camp["collected_cents"],
            "linked_cents": linked,
            "pending_cents": reste,
            "suggestions": suggestions,
        }
    finally:
        conn.close()
