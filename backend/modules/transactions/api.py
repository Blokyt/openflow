"""Transactions API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.core.auth import get_allowed_entity_ids, get_current_user, require_admin, require_entity_access
from backend.core.balance import compute_legacy_balance
from backend.core.database import get_conn, row_to_dict

def _get_reimbursement_functions():
    """Import conditionnel du module reimbursements.

    Retourne (create_advance, delete_advance, sync_pending_advance_amount)
    si le module est disponible, sinon (None, None, None).
    """
    try:
        from backend.modules.reimbursements.service import (
            create_advance,
            delete_advance,
            sync_pending_advance_amount,
        )
        return create_advance, delete_advance, sync_pending_advance_amount
    except ImportError:
        return None, None, None


router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/transactions/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
ATTACHMENTS_DIR = PROJECT_ROOT / "data" / "attachments"


def _date_in_closed_period(conn: sqlite3.Connection, date: str) -> bool:
    """Retourne True si `date` tombe dans un exercice clôturé (end_date IS NOT NULL).

    Retourne False si la table fiscal_years n'existe pas (module budget absent).
    """
    try:
        row = conn.execute(
            """SELECT 1 FROM fiscal_years
               WHERE end_date IS NOT NULL
                 AND ? BETWEEN start_date AND end_date""",
            (date,),
        ).fetchone()
        return row is not None
    except Exception:
        return False




class TransactionCreate(BaseModel):
    date: str
    label: str
    description: str = ""
    amount: int  # centimes, toujours positif ; le sens vient de from/to
    category_id: Optional[int] = None
    contact_id: Optional[int] = None
    created_by: str = ""
    from_entity_id: int
    to_entity_id: int
    payer_contact_id: Optional[int] = None


class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[int] = None  # centimes, toujours positif
    category_id: Optional[int] = None
    contact_id: Optional[int] = None
    created_by: Optional[str] = None
    from_entity_id: Optional[int] = None
    to_entity_id: Optional[int] = None
    payer_contact_id: Optional[int] = None
    # Suivi trésorier (pas une donnée comptable) : « la transaction est justifiée ».
    justified: Optional[bool] = None
    # Rapprochement forcé à la main (ex : espèces jamais passées en banque).
    reconciled_manual: Optional[bool] = None


# Champs de pur suivi : leur bascule seule ne passe pas par le verrou de clôture
# (cocher « justifié » sur une écriture d'un exercice clos n'altère aucun bilan).
_FOLLOWUP_FIELDS = {"justified", "reconciled_manual"}


# Colonnes de tri autorisées (whitelist : jamais d'ORDER BY construit depuis l'entrée brute).
_SORT_COLUMNS = {"date": "t.date", "amount": "t.amount", "label": "t.label", "id": "t.id"}


@router.get("/")
def list_transactions(
    request: Request,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    entity_id: Optional[int] = None,
    include_children: bool = False,
    reimb_status: Optional[str] = None,
    justified: Optional[int] = None,
    amount_min: Optional[int] = None,
    amount_max: Optional[int] = None,
    limit: Optional[int] = Query(None, ge=0),
    offset: int = Query(0, ge=0),
    sort_by: str = "date",
    sort_dir: str = "desc",
):
    user = get_current_user(request)
    conn = get_conn()
    try:
        allowed = get_allowed_entity_ids(conn, user)
        # Périmètre vide sans focus explicite : rien à voir, court-circuit avant
        # de construire la requête (évite un WHERE ... IN () invalide).
        if entity_id is None and allowed is not None and not allowed:
            return {"total": 0, "items": []}
        # La table attachments appartient à un module optionnel : jointure
        # conditionnelle pour ne pas casser la liste si elle n'existe pas.
        has_attachments_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'attachments'"
        ).fetchone() is not None
        attachment_col = (
            ", COALESCE(att.attachment_count, 0) AS attachment_count"
            if has_attachments_table else ", 0 AS attachment_count"
        )
        attachment_join = (
            """
            LEFT JOIN (
                SELECT transaction_id, COUNT(*) AS attachment_count
                FROM attachments
                WHERE transaction_id IS NOT NULL
                GROUP BY transaction_id
            ) att ON att.transaction_id = t.id"""
            if has_attachments_table else ""
        )
        select_cols = """SELECT t.*,
                   c.name AS category_name, c.color AS category_color,
                   ef.name AS from_entity_name, ef.color AS from_entity_color, ef.type AS from_entity_type,
                   et.name AS to_entity_name, et.color AS to_entity_color, et.type AS to_entity_type,
                   co.name AS contact_name,
                   rb.reimb_person_name, rb.reimb_status, rb.reimb_count, rb.reimb_contact_id, rb.reimb_id""" \
            + attachment_col
        from_where = """
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN entities ef ON t.from_entity_id = ef.id
            LEFT JOIN entities et ON t.to_entity_id = et.id
            LEFT JOIN contacts co ON t.contact_id = co.id
            LEFT JOIN (
                SELECT transaction_id,
                       GROUP_CONCAT(COALESCE(rco.name, r.person_name), ', ') AS reimb_person_name,
                       MIN(r.status) AS reimb_status,
                       COUNT(*) AS reimb_count,
                       MIN(r.contact_id) AS reimb_contact_id,
                       MIN(r.id) AS reimb_id
                FROM reimbursements r
                LEFT JOIN contacts rco ON r.contact_id = rco.id
                GROUP BY transaction_id
            ) rb ON rb.transaction_id = t.id""" + attachment_join + """
            WHERE 1=1"""
        params = []
        if date_from:
            from_where += " AND t.date >= ?"
            params.append(date_from)
        if date_to:
            from_where += " AND t.date <= ?"
            params.append(date_to)
        if category_id is not None:
            from_where += " AND t.category_id = ?"
            params.append(category_id)
        if search:
            from_where += """ AND (t.label LIKE ? OR t.description LIKE ?
                         OR ef.name LIKE ? OR et.name LIKE ?
                         OR c.name LIKE ? OR co.name LIKE ? OR t.date LIKE ?)"""
            s = f"%{search}%"
            params.extend([s, s, s, s, s, s, s])
        if entity_id is not None:
            if allowed is not None:
                require_entity_access(conn, user, entity_id)
            if include_children:
                rows = conn.execute(
                    """WITH RECURSIVE subtree(id) AS (
                           SELECT ? AS id
                           UNION ALL
                           SELECT e.id FROM entities e
                           INNER JOIN subtree s ON e.parent_id = s.id
                       )
                       SELECT id FROM subtree""",
                    (entity_id,),
                ).fetchall()
                entity_ids = [r[0] for r in rows]
                placeholders = ",".join("?" * len(entity_ids))
                from_where += f" AND (t.from_entity_id IN ({placeholders}) OR t.to_entity_id IN ({placeholders}))"
                params.extend(entity_ids)
                params.extend(entity_ids)
            else:
                from_where += " AND (t.from_entity_id = ? OR t.to_entity_id = ?)"
                params.extend([entity_id, entity_id])
        elif allowed is not None:
            # Pas de focus explicite : filtre implicite sur le périmètre du rôle
            # (non vide, déjà court-circuité plus haut sinon).
            placeholders = ",".join("?" * len(allowed))
            from_where += f" AND (t.from_entity_id IN ({placeholders}) OR t.to_entity_id IN ({placeholders}))"
            params.extend(list(allowed))
            params.extend(list(allowed))
        if reimb_status == "pending":
            from_where += " AND rb.reimb_status = 'pending'"
        elif reimb_status == "reimbursed":
            from_where += " AND rb.reimb_status = 'reimbursed'"
        elif reimb_status == "none":
            from_where += " AND rb.reimb_status IS NULL"
        elif reimb_status is not None:
            raise HTTPException(status_code=400, detail=f"invalid reimb_status: {reimb_status}")
        if justified is not None:
            if justified not in (0, 1):
                raise HTTPException(status_code=400, detail=f"invalid justified: {justified}")
            from_where += " AND COALESCE(t.justified, 0) = ?"
            params.append(justified)
        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            raise HTTPException(status_code=400, detail="amount_min must be <= amount_max")
        if amount_min is not None:
            from_where += " AND ABS(t.amount) >= ?"
            params.append(amount_min)
        if amount_max is not None:
            from_where += " AND ABS(t.amount) <= ?"
            params.append(amount_max)

        # Total (mêmes filtres, avant pagination).
        total = conn.execute("SELECT COUNT(*)" + from_where, params).fetchone()[0]

        # Tri serveur whitelisté + tie-breaker stable sur l'id.
        if sort_by not in _SORT_COLUMNS:
            raise HTTPException(status_code=400, detail=f"invalid sort_by: {sort_by}")
        if sort_dir not in ("asc", "desc"):
            raise HTTPException(status_code=400, detail=f"invalid sort_dir: {sort_dir}")
        direction = "ASC" if sort_dir == "asc" else "DESC"
        order_sql = f" ORDER BY {_SORT_COLUMNS[sort_by]} {direction}, t.id {direction}"

        list_sql = select_cols + from_where + order_sql
        list_params = list(params)
        if limit is not None:
            list_sql += " LIMIT ? OFFSET ?"
            list_params.extend([limit, offset])

        items = [row_to_dict(r) for r in conn.execute(list_sql, list_params).fetchall()]
        return {"total": total, "items": items}
    finally:
        conn.close()


def _assert_entity_ref(conn, field: str, value) -> None:
    """L'entité doit exister ET ne pas être agrégée.

    Une entité agrégée (ex : « BDA global ») est un regroupement/ombrelle, pas
    une contrepartie qui détient l'argent : la cibler créerait un solde propre
    fantôme incohérent avec le bilan/les rapports (qui l'excluent).
    """
    row = conn.execute("SELECT balance_mode FROM entities WHERE id = ?", (value,)).fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail=f"{field}={value} does not reference an existing entity")
    mode = row["balance_mode"] if hasattr(row, "keys") else row[0]
    if mode == "aggregate":
        raise HTTPException(
            status_code=400,
            detail=f"{field} : une entité agrégée (regroupement) ne peut pas être une contrepartie ; choisis l'entité qui détient l'argent (feuille locale ou club).",
        )


@router.post("/", status_code=201)
def create_transaction(tx: TransactionCreate, force: bool = False):
    # Convention : montant strictement positif, sens porté par from/to distincts.
    if tx.amount <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit être strictement positif")
    if tx.from_entity_id == tx.to_entity_id:
        raise HTTPException(status_code=400, detail="Les entités source et destination doivent être différentes")
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        # Verrou de clôture : la date ne doit pas tomber dans un exercice clôturé,
        # sauf si l'appelant force explicitement (force=true).
        if not force and _date_in_closed_period(conn, tx.date):
            raise HTTPException(
                status_code=409,
                detail="Exercice clôturé : modifier quand même ?",
            )
        for field, value in (("from_entity_id", tx.from_entity_id), ("to_entity_id", tx.to_entity_id)):
            _assert_entity_ref(conn, field, value)
        cur = conn.execute(
            """INSERT INTO transactions
               (date, label, description, amount, category_id, contact_id, created_by,
                from_entity_id, to_entity_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx.date,
                tx.label,
                tx.description,
                tx.amount,
                tx.category_id,
                tx.contact_id,
                tx.created_by,
                tx.from_entity_id,
                tx.to_entity_id,
                now,
                now,
            ),
        )
        tx_id = cur.lastrowid
        new_row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()

        _create_advance, _, _ = _get_reimbursement_functions()
        if _create_advance is not None:
            _create_advance(conn, tx_id, tx.payer_contact_id, now)

        conn.commit()
        return row_to_dict(new_row)
    finally:
        conn.close()


# IMPORTANT: /balance must be declared BEFORE /{tx_id} to avoid FastAPI
# treating "balance" as a tx_id path parameter.
@router.get("/balance")
def get_balance(user: dict = Depends(require_admin)):
    """Solde légal global (rétrocompatibilité). Fuite potentielle de la trésorerie
    totale de l'association à un non-admin : réservé à l'administrateur."""
    conn = get_conn()
    try:
        return compute_legacy_balance(conn, str(CONFIG_PATH))
    finally:
        conn.close()


@router.get("/{tx_id}")
def get_transaction(tx_id: int, request: Request):
    user = get_current_user(request)
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
        allowed = get_allowed_entity_ids(conn, user)
        if allowed is not None and row["from_entity_id"] not in allowed and row["to_entity_id"] not in allowed:
            raise HTTPException(status_code=403, detail="Accès refusé à cette entité")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{tx_id}")
def update_transaction(tx_id: int, tx: TransactionUpdate, force: bool = False):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")

        # Verrou de clôture : la tx existante ou la nouvelle date ne doivent pas
        # tomber dans un exercice clôturé, sauf si l'appelant force (force=true).
        # Exception : une bascule qui ne touche QUE des champs de suivi (justified)
        # n'altère aucun bilan et passe sans force.
        updates_preview = tx.model_dump(exclude_unset=True)
        only_followup = bool(updates_preview) and set(updates_preview) <= _FOLLOWUP_FIELDS
        existing_date = existing["date"]
        new_date = updates_preview.get("date", existing_date)
        if not force and not only_followup and (
            _date_in_closed_period(conn, existing_date) or _date_in_closed_period(conn, new_date)
        ):
            raise HTTPException(
                status_code=409,
                detail="Exercice clôturé : modifier quand même ?",
            )

        updates = tx.model_dump(exclude_unset=True)
        # Suivi « justifié » : booléen stocké en 0/1, horodaté quand il passe à vrai.
        if "justified" in updates:
            updates["justified"] = 1 if updates["justified"] else 0
            updates["justified_at"] = now if updates["justified"] else None
        # Rapprochement forcé à la main (0/1). N'écrase pas le rapprochement
        # automatique posé par le lien bancaire (colonne `reconciled` distincte).
        if "reconciled_manual" in updates:
            updates["reconciled_manual"] = 1 if updates["reconciled_manual"] else 0
        # Separate payer_contact_id from tx-column updates
        payer_contact_id_provided = "payer_contact_id" in updates
        payer_contact_id_value = updates.pop("payer_contact_id", None)

        if not updates and not payer_contact_id_provided:
            return row_to_dict(existing)

        for field in ("from_entity_id", "to_entity_id"):
            if field in updates:
                if updates[field] is None:
                    raise HTTPException(status_code=400, detail=f"{field} cannot be null")
                _assert_entity_ref(conn, field, updates[field])

        if "amount" in updates and updates["amount"] is not None and updates["amount"] <= 0:
            raise HTTPException(status_code=400, detail="Le montant doit être strictement positif")
        final_from = updates.get("from_entity_id", existing["from_entity_id"])
        final_to = updates.get("to_entity_id", existing["to_entity_id"])
        if final_from is not None and final_from == final_to:
            raise HTTPException(status_code=400, detail="Les entités source et destination doivent être différentes")

        if updates:
            set_clauses = ", ".join(f"{k} = ?" for k in updates)
            set_clauses += ", updated_at = ?"
            values = list(updates.values()) + [now, tx_id]
            conn.execute(
                f"UPDATE transactions SET {set_clauses} WHERE id = ?",
                values,
            )

        # Handle payer / reimbursement upsert.
        # On NE réinitialise le suivi de remboursement QUE si le payeur change
        # réellement. Une simple édition de la transaction (date, montant, libellé)
        # renvoie le même payeur : dans ce cas on PRÉSERVE le remboursement et son
        # statut (sinon un remboursement déjà traité repasserait "en attente").
        _create_adv, _delete_adv, _sync_adv = _get_reimbursement_functions()
        if payer_contact_id_provided and _delete_adv is not None:
            try:
                existing_reimb = conn.execute(
                    "SELECT contact_id FROM reimbursements WHERE transaction_id = ?",
                    (tx_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                existing_reimb = None  # table reimbursements absente
            existing_payer = existing_reimb["contact_id"] if existing_reimb else None
            payer_changed = payer_contact_id_value != existing_payer

            if payer_changed:
                # Le payeur change : l'ancien suivi devient obsolète, on le remplace.
                _delete_adv(conn, tx_id)
                if _create_adv is not None:
                    _create_adv(conn, tx_id, payer_contact_id_value, now)
            elif existing_reimb is not None and "amount" in updates:
                # Payeur inchangé : statut préservé. On resynchronise seulement le
                # montant du suivi si l'avance est encore "en attente" et que le
                # montant de la transaction vient de changer.
                if _sync_adv is not None:
                    _sync_adv(conn, tx_id, now)

        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        conn.commit()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{tx_id}")
def delete_transaction(tx_id: int, force: bool = False):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
        # Verrou de clôture, franchissable avec force=true.
        if not force and _date_in_closed_period(conn, existing["date"]):
            raise HTTPException(
                status_code=409,
                detail="Exercice clôturé : modifier quand même ?",
            )
        # Nettoyage du suivi d'avance lié à cette écriture, pour éviter les
        # orphelins (FK OFF, pas de cascade).
        _, _delete_adv, _ = _get_reimbursement_functions()
        if _delete_adv is not None:
            _delete_adv(conn, tx_id)
        # Justificatifs liés : fichiers sur disque + lignes (la cascade FK déclarée
        # n'est jamais exécutée car PRAGMA foreign_keys est OFF).
        try:
            for att in conn.execute(
                "SELECT filename FROM attachments WHERE transaction_id = ?", (tx_id,)
            ).fetchall():
                fp = ATTACHMENTS_DIR / att["filename"]
                if fp.exists():
                    try:
                        fp.unlink()
                    except OSError:
                        pass
            conn.execute("DELETE FROM attachments WHERE transaction_id = ?", (tx_id,))
        except sqlite3.OperationalError:
            pass  # module attachments absent
        # Liens HelloAsso : évite des lignes orphelines après suppression.
        try:
            conn.execute("DELETE FROM helloasso_campaign_transactions WHERE transaction_id = ?", (tx_id,))
        except sqlite3.OperationalError:
            pass  # module helloasso absent
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        conn.commit()
        return {"deleted": tx_id}
    finally:
        conn.close()
