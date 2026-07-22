"""API du rapprochement bancaire.

Modèle : chaque ligne bancaire (bank_transactions) est associée à une ou
plusieurs écritures de la compta (transactions) via une table de liaison
MANY-TO-MANY (bank_transaction_links). Une ligne est « rapprochée » quand la
somme des écritures liées égale son montant (en valeur absolue), ou quand elle
est marquée manuellement.

Convention de montants : transactions.amount est en centimes TOUJOURS positif
(le sens vient de from/to). bank_transactions.amount est SIGNÉ (+ crédit /
- débit). On rapproche donc SUM(transactions.amount) avec ABS(bank.amount).
"""
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from backend.core.auth import require_admin
from backend.core.database import get_conn, row_to_dict
from backend.modules.bank_reconciliation.parsers import ParseError, parse_statement
from backend.modules.bank_reconciliation.enablebanking import (
    EnableBankingClient, EnableBankingError, generate_keypair_and_cert, normalize_transactions,
)

router = APIRouter(dependencies=[Depends(require_admin)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Calcul du lié / restant / rapproché
# ---------------------------------------------------------------------------

def _linked_map(conn, bank_ids) -> dict:
    """Retourne {bank_transaction_id: linked_cents}.

    linked_cents = somme des montants (positifs) des écritures liées. Le JOIN
    ignore les liens orphelins (écriture supprimée) : aucun couplage dur avec
    le module transactions.
    """
    ids = list(bank_ids)
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT l.bank_transaction_id AS bid, COALESCE(SUM(t.amount), 0) AS linked
            FROM bank_transaction_links l
            JOIN transactions t ON t.id = l.transaction_id
            WHERE l.bank_transaction_id IN ({ph})
            GROUP BY l.bank_transaction_id""",
        ids,
    ).fetchall()
    return {r["bid"]: r["linked"] for r in rows}


def _reconciled_status(amount: int, linked: int, reconciled_manual) -> tuple[int, int, bool]:
    """Règle métier unique du module : une ligne bancaire (montant signé) est
    « rapprochée » quand la somme des écritures liées (positives) égale son
    montant en valeur absolue, ou quand elle est marquée manuellement.
    Renvoie (target, pending_cents, reconciled). Source de vérité unique
    consommée par la liste, les compteurs et le panneau de détail."""
    target = abs(amount)
    return target, target - linked, bool(reconciled_manual) or (linked == target)


def _enrich(bt: dict, linked: int) -> dict:
    """Ajoute linked_cents / pending_cents / reconciled à une ligne bancaire."""
    _, pending, reconciled = _reconciled_status(bt["amount"], linked, bt.get("reconciled_manual"))
    bt["linked_cents"] = linked
    bt["pending_cents"] = pending
    bt["reconciled"] = reconciled
    return bt


def _upsert_bank_rows(conn, account_id: int, rows: list, now: str) -> int:
    """Insère les lignes bancaires normalisées (ignore celles sans date), en
    évitant les doublons via UNIQUE(bank_account_id, external_id). Met à jour
    last_synced_at. Renvoie le nombre de lignes réellement importées. Partagé
    par l'import fichier et la synchronisation Enable Banking."""
    imported = 0
    for r in rows:
        if not r["booking_date"]:
            continue
        cur = conn.execute(
            """INSERT INTO bank_transactions
               (bank_account_id, external_id, booking_date, amount, currency,
                label, counterparty, reconciled_manual, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
               ON CONFLICT(bank_account_id, external_id) DO NOTHING""",
            (account_id, r["external_id"], r["booking_date"], r["amount"],
             r["currency"], r["label"], r["counterparty"], now),
        )
        imported += cur.rowcount
    conn.execute("UPDATE bank_accounts SET last_synced_at = ? WHERE id = ?", (now, account_id))
    return imported


def _enrich_all(conn, rows) -> list:
    items = [row_to_dict(r) for r in rows]
    linked = _linked_map(conn, [b["id"] for b in items])
    return [_enrich(b, linked.get(b["id"], 0)) for b in items]


def _refresh_transaction_reconciled(conn, transaction_id: int) -> None:
    """Met à jour transactions.reconciled : 1 si l'écriture a au moins une
    liaison bancaire, 0 sinon. Réutilise les colonnes vestiges reconciled /
    reconciled_at de la table transactions (migration transactions 1.4.0)."""
    has_link = conn.execute(
        "SELECT 1 FROM bank_transaction_links WHERE transaction_id = ? LIMIT 1",
        (transaction_id,),
    ).fetchone() is not None
    if has_link:
        conn.execute(
            "UPDATE transactions SET reconciled = 1, reconciled_at = ? WHERE id = ?",
            (_now(), transaction_id),
        )
    else:
        conn.execute(
            "UPDATE transactions SET reconciled = 0, reconciled_at = NULL WHERE id = ?",
            (transaction_id,),
        )


# ---------------------------------------------------------------------------
# Comptes bancaires
# ---------------------------------------------------------------------------

class AccountPayload(BaseModel):
    entity_id: int
    label: str = ""
    iban: str = ""


def _account_or_404(conn, account_id: int) -> dict:
    row = conn.execute("SELECT * FROM bank_accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Compte bancaire introuvable")
    return row_to_dict(row)


def _all_account_counters(conn) -> dict:
    """{account_id: {tx_count, to_reconcile_count}} pour tous les comptes en une
    seule requête (évite le N+1 dans la liste des comptes)."""
    rows = conn.execute(
        """SELECT bt.bank_account_id AS aid, bt.amount, bt.reconciled_manual,
                  COALESCE(SUM(t.amount), 0) AS linked
           FROM bank_transactions bt
           LEFT JOIN bank_transaction_links l ON l.bank_transaction_id = bt.id
           LEFT JOIN transactions t ON t.id = l.transaction_id
           GROUP BY bt.id"""
    ).fetchall()
    counters: dict = {}
    for r in rows:
        c = counters.setdefault(r["aid"], {"tx_count": 0, "to_reconcile_count": 0})
        c["tx_count"] += 1
        _, _, reconciled = _reconciled_status(r["amount"], r["linked"], r["reconciled_manual"])
        if not reconciled:
            c["to_reconcile_count"] += 1
    return counters


@router.get("/accounts")
def list_accounts():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT a.*, e.name AS entity_name
               FROM bank_accounts a
               LEFT JOIN entities e ON e.id = a.entity_id
               ORDER BY a.label, a.id"""
        ).fetchall()
        counters = _all_account_counters(conn)
        accounts = []
        for r in rows:
            acc = row_to_dict(r)
            acc.update(counters.get(acc["id"], {"tx_count": 0, "to_reconcile_count": 0}))
            accounts.append(acc)
        return accounts
    finally:
        conn.close()


@router.post("/accounts", status_code=201)
def create_account(payload: AccountPayload):
    conn = get_conn()
    try:
        ent = conn.execute(
            "SELECT id, type FROM entities WHERE id = ?", (payload.entity_id,)
        ).fetchone()
        if ent is None:
            raise HTTPException(status_code=404, detail="Entité introuvable")
        if ent["type"] != "internal":
            raise HTTPException(status_code=400, detail="Le compte doit être rattaché à une entité interne")
        cur = conn.execute(
            """INSERT INTO bank_accounts (entity_id, label, iban, source, created_at)
               VALUES (?, ?, ?, 'file', ?)""",
            (payload.entity_id, payload.label.strip(), payload.iban.strip(), _now()),
        )
        conn.commit()
        acc = _account_or_404(conn, cur.lastrowid)
        acc.update({"tx_count": 0, "to_reconcile_count": 0})
        return acc
    finally:
        conn.close()


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int):
    """Supprime un compte, ses lignes bancaires et leurs liaisons. Les
    écritures compta redeviennent non rapprochées si elles n'ont plus de lien."""
    conn = get_conn()
    try:
        _account_or_404(conn, account_id)
        bank_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM bank_transactions WHERE bank_account_id = ?", (account_id,)
        ).fetchall()]
        affected_tx = []
        if bank_ids:
            ph = ",".join("?" * len(bank_ids))
            affected_tx = [r["transaction_id"] for r in conn.execute(
                f"SELECT DISTINCT transaction_id FROM bank_transaction_links WHERE bank_transaction_id IN ({ph})",
                bank_ids,
            ).fetchall()]
            conn.execute(f"DELETE FROM bank_transaction_links WHERE bank_transaction_id IN ({ph})", bank_ids)
            conn.execute("DELETE FROM bank_transactions WHERE bank_account_id = ?", (account_id,))
        conn.execute("DELETE FROM bank_accounts WHERE id = ?", (account_id,))
        for tx_id in affected_tx:
            _refresh_transaction_reconciled(conn, tx_id)
        conn.commit()
        return {"deleted": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Import d'un relevé (CSV / OFX)
# ---------------------------------------------------------------------------

@router.post("/accounts/{account_id}/import")
async def import_statement(account_id: int, file: UploadFile = File(...)):
    conn = get_conn()
    try:
        _account_or_404(conn, account_id)
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Fichier vide")
        try:
            rows = parse_statement(file.filename or "", content)
        except ParseError as e:
            raise HTTPException(status_code=400, detail=str(e))
        now = _now()
        imported = _upsert_bank_rows(conn, account_id, rows, now)
        conn.commit()
        return {"imported": imported, "skipped": len(rows) - imported, "total": len(rows)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lecture des lignes bancaires
# ---------------------------------------------------------------------------

@router.get("/transactions")
def list_transactions(
    account_id: int,
    status: str = Query(default="pending", pattern="^(pending|reconciled|all)$"),
):
    conn = get_conn()
    try:
        _account_or_404(conn, account_id)
        rows = conn.execute(
            "SELECT * FROM bank_transactions WHERE bank_account_id = ? ORDER BY booking_date DESC, id DESC",
            (account_id,),
        ).fetchall()
        items = _enrich_all(conn, rows)
        if status == "pending":
            items = [b for b in items if not b["reconciled"]]
        elif status == "reconciled":
            items = [b for b in items if b["reconciled"]]
        return items
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Association d'écritures à une ligne bancaire (many-to-many)
# ---------------------------------------------------------------------------

def _bank_or_404(conn, bank_transaction_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM bank_transactions WHERE id = ?", (bank_transaction_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Ligne bancaire introuvable")
    return row_to_dict(row)


def _links_payload(conn, bank_transaction_id: int, bt: dict) -> dict:
    rows = conn.execute(
        """SELECT l.id AS link_id, t.id AS transaction_id, t.date, t.label, t.amount,
                  t.from_entity_id, t.to_entity_id,
                  fe.name AS from_entity_name, te.name AS to_entity_name
           FROM bank_transaction_links l
           JOIN transactions t ON t.id = l.transaction_id
           LEFT JOIN entities fe ON fe.id = t.from_entity_id
           LEFT JOIN entities te ON te.id = t.to_entity_id
           WHERE l.bank_transaction_id = ?
           ORDER BY t.date, t.id""",
        (bank_transaction_id,),
    ).fetchall()
    links = [row_to_dict(r) for r in rows]
    linked = sum(l["amount"] for l in links)
    _, pending, reconciled = _reconciled_status(bt["amount"], linked, bt.get("reconciled_manual"))
    return {
        "bank_transaction_id": bank_transaction_id,
        "amount": bt["amount"],
        "linked_cents": linked,
        "pending_cents": pending,
        "reconciled": reconciled,
        "reconciled_manual": bool(bt.get("reconciled_manual")),
        "links": links,
    }


class LinkPayload(BaseModel):
    transaction_id: int


@router.get("/transactions/{bank_transaction_id}/links")
def list_links(bank_transaction_id: int):
    conn = get_conn()
    try:
        bt = _bank_or_404(conn, bank_transaction_id)
        return _links_payload(conn, bank_transaction_id, bt)
    finally:
        conn.close()


@router.post("/transactions/{bank_transaction_id}/links", status_code=201)
def add_link(bank_transaction_id: int, payload: LinkPayload):
    """Associe une écriture à la ligne bancaire. Pas d'exclusivité : une même
    écriture peut être répartie sur plusieurs lignes bancaires (division), et
    une ligne bancaire peut regrouper plusieurs écritures (regroupement)."""
    conn = get_conn()
    try:
        bt = _bank_or_404(conn, bank_transaction_id)
        tx = conn.execute(
            "SELECT id FROM transactions WHERE id = ?", (payload.transaction_id,)
        ).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail="Écriture introuvable")
        try:
            conn.execute(
                """INSERT INTO bank_transaction_links
                   (bank_transaction_id, transaction_id, created_at) VALUES (?, ?, ?)""",
                (bank_transaction_id, payload.transaction_id, _now()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Cette écriture est déjà associée à cette ligne bancaire")
        _refresh_transaction_reconciled(conn, payload.transaction_id)
        conn.commit()
        return _links_payload(conn, bank_transaction_id, bt)
    finally:
        conn.close()


@router.delete("/transactions/{bank_transaction_id}/links/{transaction_id}")
def remove_link(bank_transaction_id: int, transaction_id: int):
    conn = get_conn()
    try:
        bt = _bank_or_404(conn, bank_transaction_id)
        cur = conn.execute(
            "DELETE FROM bank_transaction_links WHERE bank_transaction_id = ? AND transaction_id = ?",
            (bank_transaction_id, transaction_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Association introuvable")
        _refresh_transaction_reconciled(conn, transaction_id)
        conn.commit()
        return _links_payload(conn, bank_transaction_id, bt)
    finally:
        conn.close()


class MarkPayload(BaseModel):
    reconciled: bool


@router.post("/transactions/{bank_transaction_id}/mark")
def mark_reconciled(bank_transaction_id: int, payload: MarkPayload):
    """Force ou annule le marquage manuel « rapprochée » (cas où les montants
    ne collent pas exactement mais où le trésorier valide le rapprochement)."""
    conn = get_conn()
    try:
        _bank_or_404(conn, bank_transaction_id)
        conn.execute(
            "UPDATE bank_transactions SET reconciled_manual = ? WHERE id = ?",
            (1 if payload.reconciled else 0, bank_transaction_id),
        )
        conn.commit()
        bt = _bank_or_404(conn, bank_transaction_id)
        return _links_payload(conn, bank_transaction_id, bt)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Suggestions d'écritures à associer
# ---------------------------------------------------------------------------

@router.get("/transactions/{bank_transaction_id}/suggestions")
def suggestions(bank_transaction_id: int, limit: int = Query(default=20, ge=1, le=200)):
    """Propose les écritures non encore liées à CETTE ligne, du même sens
    (crédit → recette externe→interne ; débit → dépense interne→externe),
    triées « au plus proche inférieurement » du montant restant à couvrir."""
    conn = get_conn()
    try:
        bt = _bank_or_404(conn, bank_transaction_id)
        linked = _linked_map(conn, [bank_transaction_id]).get(bank_transaction_id, 0)
        reste = abs(bt["amount"]) - linked

        internal_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM entities WHERE type = 'internal'"
        ).fetchall()]
        results = []
        if internal_ids:
            ph = ",".join("?" * len(internal_ids))
            if bt["amount"] >= 0:
                # Crédit bancaire → recette : entité externe -> interne.
                direction = f"t.to_entity_id IN ({ph}) AND (t.from_entity_id IS NULL OR t.from_entity_id NOT IN ({ph}))"
            else:
                # Débit bancaire → dépense : entité interne -> externe.
                direction = f"t.from_entity_id IN ({ph}) AND (t.to_entity_id IS NULL OR t.to_entity_id NOT IN ({ph}))"
            rows = conn.execute(
                f"""SELECT t.id AS transaction_id, t.date, t.label, t.amount,
                           t.from_entity_id, t.to_entity_id,
                           fe.name AS from_entity_name, te.name AS to_entity_name
                    FROM transactions t
                    LEFT JOIN entities fe ON fe.id = t.from_entity_id
                    LEFT JOIN entities te ON te.id = t.to_entity_id
                    WHERE {direction}
                      AND t.id NOT IN (
                          SELECT transaction_id FROM bank_transaction_links
                          WHERE bank_transaction_id = ?)
                    ORDER BY (t.amount > ?) ASC, ABS(t.amount - ?) ASC, t.date DESC
                    LIMIT ?""",
                internal_ids + internal_ids + [bank_transaction_id, reste, reste, limit],
            ).fetchall()
            results = [row_to_dict(r) for r in rows]

        return {
            "bank_transaction_id": bank_transaction_id,
            "amount": bt["amount"],
            "linked_cents": linked,
            "pending_cents": reste,
            "suggestions": results,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Connecteur Enable Banking (Lot 2) — agrégation automatique PSD2
# ---------------------------------------------------------------------------

CONSENT_DAYS = 90


def _load_eb_config(conn):
    return conn.execute("SELECT * FROM bank_reconciliation_config WHERE id = 1").fetchone()


def _build_eb_client(conn):
    row = _load_eb_config(conn)
    if row is None:
        raise HTTPException(status_code=400, detail="Connecteur Enable Banking non configuré")
    d = row_to_dict(row)
    if not (d["application_id"] and d["private_key"]):
        raise HTTPException(status_code=400, detail="Configuration Enable Banking incomplète")
    return EnableBankingClient(d["application_id"], d["private_key"]), d


class EBConfigPayload(BaseModel):
    application_id: str
    private_key: str = ""
    redirect_url: str = ""


def _suggested_redirect(request: Request) -> str:
    """URL de redirection à déclarer dans Enable Banking. La Production impose
    le schéma https ; OpenFlow tourne en http local, mais la saisie manuelle du
    code d'autorisation gère ce cas (la page de retour n'a pas besoin de se
    charger)."""
    base = request.base_url  # ex : http://127.0.0.1:8000/
    host = base.hostname or "127.0.0.1"
    port = f":{base.port}" if base.port else ""
    return f"https://{host}{port}/bank-reconciliation"


@router.get("/config")
def get_config(request: Request):
    conn = get_conn()
    try:
        row = _load_eb_config(conn)
        if row is None:
            return {"configured": False, "application_id": "", "has_key": False,
                    "certificate": "", "redirect_url": "", "suggested_redirect_url": _suggested_redirect(request)}
        d = row_to_dict(row)
        return {
            "configured": bool(d["application_id"] and d["private_key"]),
            "application_id": d["application_id"],
            "has_key": bool(d["private_key"]),
            "certificate": d.get("public_cert", "") or "",
            "redirect_url": d["redirect_url"],
            "suggested_redirect_url": _suggested_redirect(request),
        }
    finally:
        conn.close()


@router.post("/config/generate-key")
def generate_key(request: Request):
    """Génère la paire clé/certificat directement dans OpenFlow et la stocke.
    Renvoie le certificat public à recopier dans Enable Banking et l'URL de
    redirection à y déclarer. Réinitialise l'Application ID (une nouvelle clé
    implique un nouvel enregistrement d'application côté Enable Banking)."""
    private_pem, cert_pem = generate_keypair_and_cert()
    conn = get_conn()
    try:
        existing = _load_eb_config(conn)
        redirect = _suggested_redirect(request)
        if existing is not None:
            existing_redirect = row_to_dict(existing).get("redirect_url", "")
            if existing_redirect:
                redirect = existing_redirect
        conn.execute(
            """INSERT INTO bank_reconciliation_config (id, application_id, private_key, public_cert, redirect_url, updated_at)
               VALUES (1, '', ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   application_id = '',
                   private_key = excluded.private_key,
                   public_cert = excluded.public_cert,
                   redirect_url = excluded.redirect_url,
                   updated_at = excluded.updated_at""",
            (private_pem, cert_pem, redirect, _now()),
        )
        conn.commit()
        return {"certificate": cert_pem, "redirect_url": redirect}
    finally:
        conn.close()


@router.put("/config")
def put_config(payload: EBConfigPayload):
    conn = get_conn()
    try:
        existing = _load_eb_config(conn)
        # Clé vide + config existante -> on conserve la clé déjà enregistrée
        # (permet de modifier l'URL de redirection sans re-saisir la clé).
        private_key = payload.private_key.strip()
        if not private_key and existing is not None:
            private_key = row_to_dict(existing)["private_key"]
        conn.execute(
            """INSERT INTO bank_reconciliation_config (id, application_id, private_key, redirect_url, updated_at)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   application_id = excluded.application_id,
                   private_key = excluded.private_key,
                   redirect_url = excluded.redirect_url,
                   updated_at = excluded.updated_at""",
            (payload.application_id.strip(), private_key, payload.redirect_url.strip(), _now()),
        )
        conn.commit()
        return {"configured": bool(payload.application_id.strip() and private_key)}
    finally:
        conn.close()


@router.get("/banks")
def list_banks(country: str = Query(default="FR")):
    """Liste les banques (ASPSP) disponibles pour un pays, pour choisir la sienne."""
    conn = get_conn()
    try:
        client, _ = _build_eb_client(conn)
        try:
            aspsps = client.get_aspsps(country)
        except EnableBankingError as e:
            raise HTTPException(status_code=502, detail=str(e))
        return [{"name": a.get("name"), "country": a.get("country"), "logo": a.get("logo")} for a in aspsps]
    finally:
        conn.close()


class ConnectPayload(BaseModel):
    aspsp_name: str
    aspsp_country: str = "FR"


@router.post("/accounts/{account_id}/connect")
def connect_account(account_id: int, payload: ConnectPayload):
    """Démarre l'autorisation : renvoie l'URL de redirection SCA vers la banque."""
    conn = get_conn()
    try:
        _account_or_404(conn, account_id)
        client, cfg = _build_eb_client(conn)
        if not cfg["redirect_url"]:
            raise HTTPException(status_code=400, detail="URL de redirection non configurée")
        # state = account_id + jeton : permet d'attacher le code au bon compte au retour.
        state = f"{account_id}.{secrets.token_urlsafe(16)}"
        valid_until = (datetime.now(timezone.utc) + timedelta(days=CONSENT_DAYS)).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        try:
            res = client.start_auth(payload.aspsp_name, payload.aspsp_country,
                                    cfg["redirect_url"], state, valid_until)
        except EnableBankingError as e:
            raise HTTPException(status_code=502, detail=str(e))
        if not res.get("url"):
            raise HTTPException(status_code=502, detail="Enable Banking n'a pas renvoyé d'URL d'autorisation")
        return {"url": res["url"], "state": state, "authorization_id": res.get("authorization_id", "")}
    finally:
        conn.close()


class FinalizePayload(BaseModel):
    code: str


@router.post("/accounts/{account_id}/finalize")
def finalize_account(account_id: int, payload: FinalizePayload):
    """Échange le code d'autorisation contre une session et rattache le compte
    bancaire distant (par IBAN si connu, sinon le premier compte renvoyé)."""
    conn = get_conn()
    try:
        acc = _account_or_404(conn, account_id)
        client, _ = _build_eb_client(conn)
        try:
            session = client.create_session(payload.code)
        except EnableBankingError as e:
            raise HTTPException(status_code=502, detail=str(e))
        accounts = session.get("accounts") or []
        if not accounts:
            raise HTTPException(status_code=502, detail="Aucun compte renvoyé par la banque")
        chosen = None
        if acc["iban"]:
            norm = acc["iban"].replace(" ", "").upper()
            for a in accounts:
                iban = ((a.get("account_id") or {}).get("iban") or "").replace(" ", "").upper()
                if iban and iban == norm:
                    chosen = a
                    break
        chosen = chosen or accounts[0]
        iban = (chosen.get("account_id") or {}).get("iban") or acc["iban"]
        expires = (datetime.now(timezone.utc) + timedelta(days=CONSENT_DAYS)).replace(microsecond=0).isoformat()
        conn.execute(
            """UPDATE bank_accounts
               SET source = 'enablebanking', eb_session_id = ?, eb_account_id = ?, iban = ?, consent_expires_at = ?
               WHERE id = ?""",
            (session.get("session_id", ""), chosen.get("uid", ""), iban, expires, account_id),
        )
        conn.commit()
        out = _account_or_404(conn, account_id)
        out["accounts_available"] = len(accounts)
        return out
    finally:
        conn.close()


@router.post("/accounts/{account_id}/sync")
def sync_account(account_id: int):
    """Tire les transactions du compte connecté (fenêtre ~90 jours) et les
    upsert dans bank_transactions (idempotent via external_id)."""
    conn = get_conn()
    try:
        acc = _account_or_404(conn, account_id)
        if acc["source"] != "enablebanking" or not acc["eb_account_id"]:
            raise HTTPException(status_code=400, detail="Ce compte n'est pas connecté à Enable Banking")
        client, _ = _build_eb_client(conn)
        date_from = (datetime.now(timezone.utc) - timedelta(days=CONSENT_DAYS)).strftime("%Y-%m-%d")
        try:
            raw = client.get_transactions(acc["eb_account_id"], date_from=date_from)
        except EnableBankingError as e:
            raise HTTPException(status_code=502, detail=str(e))
        rows = normalize_transactions(raw)
        now = _now()
        imported = _upsert_bank_rows(conn, account_id, rows, now)
        conn.commit()
        return {"imported": imported, "skipped": len(rows) - imported, "total": len(rows)}
    finally:
        conn.close()
