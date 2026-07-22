"""API Trésorerie : poches (compte / livret / caisse) et transferts inter-poches.

Modèle : le total de la trésorerie se répartit en poches. Le solde d'une poche
= reference_cents (solde fixé à un instant t) + net des transferts (entrants -
sortants). Un transfert déplace de l'argent d'une poche à l'autre sans changer
le total. Le compte peut être relié à un compte bancaire (module
bank_reconciliation) pour afficher l'écart avec le solde réel.
"""
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.auth import require_admin
from backend.core.database import get_conn, row_to_dict

router = APIRouter(dependencies=[Depends(require_admin)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Calcul des soldes
# ---------------------------------------------------------------------------

def _transfers_net(conn) -> dict:
    """{pocket_id: solde net des transferts} (entrants - sortants)."""
    net: dict = {}
    for r in conn.execute(
        "SELECT from_pocket_id AS f, to_pocket_id AS t, amount_cents AS a FROM pocket_transfers"
    ).fetchall():
        net[r["f"]] = net.get(r["f"], 0) - r["a"]
        net[r["t"]] = net.get(r["t"], 0) + r["a"]
    return net


def _bank_balance(conn, bank_account_id) -> int | None:
    """Solde réel du compte bancaire lié, si le module bank_reconciliation est
    présent et le compte a été synchronisé. None sinon (couplage souple)."""
    if not bank_account_id:
        return None
    try:
        row = conn.execute(
            "SELECT balance_cents FROM bank_accounts WHERE id = ?", (bank_account_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["balance_cents"] if row else None


def _pocket_or_404(conn, pocket_id: int) -> dict:
    row = conn.execute("SELECT * FROM pockets WHERE id = ?", (pocket_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Poche introuvable")
    return row_to_dict(row)


def _pockets_payload(conn) -> dict:
    net = _transfers_net(conn)
    rows = conn.execute("SELECT * FROM pockets ORDER BY position, id").fetchall()
    pockets = []
    for r in rows:
        p = row_to_dict(r)
        p["balance_cents"] = p["reference_cents"] + net.get(p["id"], 0)
        p["bank_balance_cents"] = _bank_balance(conn, p["bank_account_id"])
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
            # 0 = délier
            fields.append("bank_account_id = ?"); values.append(payload.bank_account_id or None)
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
        has_transfer = conn.execute(
            "SELECT 1 FROM pocket_transfers WHERE from_pocket_id = ? OR to_pocket_id = ? LIMIT 1",
            (pocket_id, pocket_id),
        ).fetchone()
        if has_transfer:
            raise HTTPException(status_code=409, detail="Poche utilisée par des transferts : supprime-les d'abord")
        conn.execute("DELETE FROM pockets WHERE id = ?", (pocket_id,))
        conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()


@router.post("/pockets/{pocket_id}/align-bank")
def align_bank(pocket_id: int):
    """Ajuste la référence de la poche pour que son solde affiché égale le solde
    réel remonté par la banque (absorbe l'écart)."""
    conn = get_conn()
    try:
        p = _pocket_or_404(conn, pocket_id)
        bank = _bank_balance(conn, p["bank_account_id"])
        if bank is None:
            raise HTTPException(status_code=400, detail="Cette poche n'est pas reliée à un compte bancaire synchronisé")
        net = _transfers_net(conn).get(pocket_id, 0)
        # balance = reference + net doit valoir bank -> reference = bank - net
        conn.execute(
            "UPDATE pockets SET reference_cents = ?, reference_date = ? WHERE id = ?",
            (bank - net, datetime.now(timezone.utc).strftime("%Y-%m-%d"), pocket_id),
        )
        conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Transferts inter-poches
# ---------------------------------------------------------------------------

class TransferPayload(BaseModel):
    from_pocket_id: int
    to_pocket_id: int
    amount_cents: int
    date: str
    label: str = ""


@router.get("/transfers")
def list_transfers(limit: int = 100):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT tr.*, pf.name AS from_name, pt.name AS to_name
               FROM pocket_transfers tr
               LEFT JOIN pockets pf ON pf.id = tr.from_pocket_id
               LEFT JOIN pockets pt ON pt.id = tr.to_pocket_id
               ORDER BY tr.date DESC, tr.id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/transfers", status_code=201)
def create_transfer(payload: TransferPayload):
    if payload.from_pocket_id == payload.to_pocket_id:
        raise HTTPException(status_code=400, detail="Les poches source et destination doivent être différentes")
    if payload.amount_cents <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit être positif")
    if not payload.date:
        raise HTTPException(status_code=400, detail="Date requise")
    conn = get_conn()
    try:
        _pocket_or_404(conn, payload.from_pocket_id)
        _pocket_or_404(conn, payload.to_pocket_id)
        conn.execute(
            """INSERT INTO pocket_transfers (from_pocket_id, to_pocket_id, amount_cents, date, label, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (payload.from_pocket_id, payload.to_pocket_id, payload.amount_cents,
             payload.date, payload.label.strip(), _now()),
        )
        conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()


@router.delete("/transfers/{transfer_id}")
def delete_transfer(transfer_id: int):
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM pocket_transfers WHERE id = ?", (transfer_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transfert introuvable")
        conn.commit()
        return _pockets_payload(conn)
    finally:
        conn.close()
