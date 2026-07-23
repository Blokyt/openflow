"""Calcul du solde Trésorerie, réutilisable hors du routeur.

La Trésorerie (poches compte / livret / caisse) est la source de vérité unique
de « combien l'asso a et où ». Son total sert d'ancrage au solde courant affiché
par le dashboard : plus de solde de référence indépendant côté entité racine, le
solde suit la Trésorerie qui évolue comme elle évolue.

Centraliser ce calcul ici évite que le dashboard ré-écrive la logique de solde
des poches (même patron que reimbursements/service.py).
"""
import sqlite3


def _has_pockets(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pockets'"
    ).fetchone()
    return row is not None


def bank_balance_cents(conn: sqlite3.Connection, bank_account_id) -> int | None:
    """Solde remonté par la banque pour un compte, ou None si indisponible."""
    if not bank_account_id:
        return None
    try:
        row = conn.execute(
            "SELECT balance_cents FROM bank_accounts WHERE id = ?", (bank_account_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["balance_cents"] if row else None


def pocket_balance_cents(conn: sqlite3.Connection, pocket, movements) -> int:
    """Solde d'une poche : solde banque si reliée, sinon référence + mouvements.

    `movements` : lignes pré-chargées (clés f=from, t=to, a=amount, d=date) pour
    ne pas re-requêter à chaque poche.
    """
    if pocket["bank_account_id"] is not None:
        bank = bank_balance_cents(conn, pocket["bank_account_id"])
        return bank if bank is not None else 0
    ref_date = pocket["reference_date"] or ""
    net = 0
    for m in movements:
        if m["d"] < ref_date:
            continue
        if m["t"] == pocket["id"]:
            net += m["a"]
        if m["f"] == pocket["id"]:
            net -= m["a"]
    return pocket["reference_cents"] + net


def _is_configured(conn: sqlite3.Connection) -> bool:
    """La Trésorerie est-elle réellement utilisée ?

    Les trois poches par défaut (Compte / Livret / Caisse) sont créées vides à
    l'installation : leur total 0 ne doit pas être pris pour un vrai solde. On
    considère la Trésorerie configurée dès qu'une poche porte un solde de
    référence (date posée) ou un lien bancaire, ou qu'un mouvement existe.
    """
    pocket = conn.execute(
        "SELECT 1 FROM pockets "
        "WHERE bank_account_id IS NOT NULL OR reference_date != '' LIMIT 1"
    ).fetchone()
    if pocket is not None:
        return True
    return conn.execute("SELECT 1 FROM pocket_movements LIMIT 1").fetchone() is not None


def treasury_total_cents(conn: sqlite3.Connection) -> int | None:
    """Total de toutes les poches en centimes.

    Renvoie None si la Trésorerie n'est pas configurée (table absente, aucune
    poche, ou poches par défaut encore vierges) : dans ce cas le dashboard reste
    sur le calcul par référence d'entité.
    """
    if not _has_pockets(conn):
        return None
    if not _is_configured(conn):
        return None
    pockets = conn.execute("SELECT * FROM pockets").fetchall()
    movements = conn.execute(
        "SELECT from_pocket_id AS f, to_pocket_id AS t, amount_cents AS a, date AS d "
        "FROM pocket_movements"
    ).fetchall()
    return sum(pocket_balance_cents(conn, p, movements) for p in pockets)


def siblings_total_cents(conn: sqlite3.Connection, entity_id: int) -> int:
    """Somme des soldes consolidés des entités SŒURS de `entity_id`.

    Sœurs = autres enfants internes du même parent (les clubs, quand entity_id
    est la feuille résiduelle « BDA local »). Import local de
    compute_consolidated_balance pour garder le service chargeable seul.
    """
    from backend.core.balance import compute_consolidated_balance

    row = conn.execute("SELECT parent_id FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not row:
        return 0
    parent_id = row["parent_id"] if hasattr(row, "keys") else row[0]
    if parent_id is None:
        return 0
    total = 0
    siblings = conn.execute(
        "SELECT id FROM entities WHERE parent_id = ? AND type = 'internal' AND id != ?",
        (parent_id, entity_id),
    ).fetchall()
    for s in siblings:
        sid = s["id"] if hasattr(s, "keys") else s[0]
        total += compute_consolidated_balance(conn, sid)["consolidated_balance"]
    return total


def residual_balance_cents(conn: sqlite3.Connection, entity_id: int) -> int | None:
    """Solde DÉDUIT d'une feuille résiduelle (ex : BDA local).

    = total Trésorerie − Σ soldes des sœurs (les clubs). L'asso ne saisit que
    les soldes des clubs ; l'argent propre de la feuille résiduelle se déduit du
    total réel en Trésorerie. Renvoie None si la Trésorerie n'est pas configurée
    (repli sur le calcul par référence).
    """
    total = treasury_total_cents(conn)
    if total is None:
        return None
    return total - siblings_total_cents(conn, entity_id)
