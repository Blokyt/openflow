"""API Trésorerie : poches (compte / livret / caisse) et mouvements.

Source de vérité unique de "combien d'argent l'asso a et où".

Deux modes de poche, jamais les deux à la fois :
- reliée à un compte bancaire (bank_account_id) : solde = solde de la banque,
  en lecture seule (toujours synchronisé) ;
- manuelle : solde = reference_cents (solde fixé à un instant t) + net des
  mouvements. Seules les poches manuelles participent aux mouvements.

Mouvements (from/to nullable) : rentrée (to seul), sortie (from seul),
transfert (from + to). Une rentrée augmente le total, une sortie le diminue,
un transfert le conserve.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.auth import require_admin
from backend.core.database import get_conn, row_to_dict
from backend.modules.treasury.service import bank_balance_cents, pocket_balance_cents

router = APIRouter(dependencies=[Depends(require_admin)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Soldes
# ---------------------------------------------------------------------------

def _pocket_or_404(conn, pocket_id: int) -> dict:
    row = conn.execute("SELECT * FROM pockets WHERE id = ?", (pocket_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Poche introuvable")
    return row_to_dict(row)


def _pockets_payload(conn) -> dict:
    movements = conn.execute(
        "SELECT from_pocket_id AS f, to_pocket_id AS t, amount_cents AS a, date AS d FROM pocket_movements"
    ).fetchall()
    rows = conn.execute("SELECT * FROM pockets ORDER BY position, id").fetchall()
    pockets = []
    for r in rows:
        p = row_to_dict(r)
        linked = p["bank_account_id"] is not None
        p["bank_linked"] = linked
        if linked:
            bank = bank_balance_cents(conn, p["bank_account_id"])
            p["bank_balance_cents"] = bank
            p["synced"] = bank is not None
        else:
            p["bank_balance_cents"] = None
            p["synced"] = None
        # Solde d'une poche : banque si reliée, sinon référence + mouvements.
        p["balance_cents"] = pocket_balance_cents(conn, p, movements)
        pockets.append(p)
    return {"pockets": pockets, "total_cents": sum(p["balance_cents"] for p in pockets)}


@router.get("/pockets")
def list_pockets():
    conn = get_conn()
    try:
        return _pockets_payload(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Gestion des poches
# ---------------------------------------------------------------------------

class PocketCreate(BaseModel):
    name: str


class PocketUpdate(BaseModel):
    name: str | None = None
    reference_cents: int | None = None
    reference_date: str | None = None
    bank_account_id: int | None = None
    annual_rate: float | None = None


@router.post("/pockets", status_code=201)
def create_pocket(payload: PocketCreate):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de poche requis")
    conn = get_conn()
    try:
        pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM pockets").fetchone()["p"]
        conn.execute(
            "INSERT INTO pockets (name, position, reference_cents, reference_date, created_at) VALUES (?, ?, 0, '', ?)",
            (name, pos, _now()),
        )
        conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()


@router.put("/pockets/{pocket_id}")
def update_pocket(pocket_id: int, payload: PocketUpdate):
    conn = get_conn()
    try:
        _pocket_or_404(conn, pocket_id)
        fields, values = [], []
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Nom de poche requis")
            fields.append("name = ?"); values.append(name)
        if payload.reference_cents is not None:
            fields.append("reference_cents = ?"); values.append(payload.reference_cents)
        if payload.reference_date is not None:
            fields.append("reference_date = ?"); values.append(payload.reference_date)
        if payload.bank_account_id is not None:
            acc = payload.bank_account_id or None
            # Un compte bancaire ne peut alimenter qu'UNE poche : on délie toute
            # autre poche déjà reliée à ce compte (évite deux poches identiques).
            if acc is not None:
                conn.execute(
                    "UPDATE pockets SET bank_account_id = NULL WHERE bank_account_id = ? AND id != ?",
                    (acc, pocket_id),
                )
            fields.append("bank_account_id = ?"); values.append(acc)
        if payload.annual_rate is not None:
            fields.append("annual_rate = ?"); values.append(payload.annual_rate if payload.annual_rate > 0 else None)
        if fields:
            values.append(pocket_id)
            conn.execute(f"UPDATE pockets SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()


@router.delete("/pockets/{pocket_id}")
def delete_pocket(pocket_id: int):
    conn = get_conn()
    try:
        _pocket_or_404(conn, pocket_id)
        used = conn.execute(
            "SELECT 1 FROM pocket_movements WHERE from_pocket_id = ? OR to_pocket_id = ? LIMIT 1",
            (pocket_id, pocket_id),
        ).fetchone()
        if used:
            raise HTTPException(status_code=409, detail="Poche utilisée par des mouvements : supprime-les d'abord")
        conn.execute("DELETE FROM pockets WHERE id = ?", (pocket_id,))
        conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Mouvements (rentrée / sortie / transfert)
# ---------------------------------------------------------------------------

class MovementPayload(BaseModel):
    from_pocket_id: int | None = None
    to_pocket_id: int | None = None
    amount_cents: int
    date: str
    label: str = ""


def _assert_manual(conn, pocket_id: int):
    """Une poche reliée à la banque est pilotée par la banque : elle ne peut pas
    être source/destination d'un mouvement manuel (évite le double comptage)."""
    p = _pocket_or_404(conn, pocket_id)
    if p["bank_account_id"] is not None:
        raise HTTPException(
            status_code=400,
            detail=f"La poche « {p['name']} » est synchronisée avec la banque : son solde vient de la banque, pas des mouvements manuels.",
        )


@router.get("/movements")
def list_movements(limit: int = 100):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.*, pf.name AS from_name, pt.name AS to_name
               FROM pocket_movements m
               LEFT JOIN pockets pf ON pf.id = m.from_pocket_id
               LEFT JOIN pockets pt ON pt.id = m.to_pocket_id
               ORDER BY m.date DESC, m.id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/movements", status_code=201)
def create_movement(payload: MovementPayload):
    if payload.amount_cents <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit être positif")
    if payload.from_pocket_id is None and payload.to_pocket_id is None:
        raise HTTPException(status_code=400, detail="Indique au moins une poche (source ou destination)")
    if payload.from_pocket_id is not None and payload.from_pocket_id == payload.to_pocket_id:
        raise HTTPException(status_code=400, detail="Les poches source et destination doivent différer")
    if not payload.date:
        raise HTTPException(status_code=400, detail="Date requise")
    conn = get_conn()
    try:
        if payload.from_pocket_id is not None:
            _assert_manual(conn, payload.from_pocket_id)
        if payload.to_pocket_id is not None:
            _assert_manual(conn, payload.to_pocket_id)
        conn.execute(
            """INSERT INTO pocket_movements (from_pocket_id, to_pocket_id, amount_cents, date, label, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (payload.from_pocket_id, payload.to_pocket_id, payload.amount_cents,
             payload.date, payload.label.strip(), _now()),
        )
        conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()


@router.delete("/movements/{movement_id}")
def delete_movement(movement_id: int):
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM pocket_movements WHERE id = ?", (movement_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mouvement introuvable")
        conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()
