"""Service partagé du module reimbursements : suivi d'avance de frais.

Une transaction payée par un membre (avance de frais) porte une fiche de
remboursement 'pending' dans la table reimbursements. Ce service est le seul
point d'écriture de ce lien : il est utilisé par le module transactions
(saisie directe, édition, suppression) et par le module submissions
(approbation d'une soumission portant un payeur).

La table appartient à un module optionnel : si elle n'existe pas (module
jamais migré), chaque fonction est un no-op silencieux, comme les gardes
try/except historiques du module transactions.
"""
import sqlite3


def create_advance(conn, tx_id: int, payer_contact_id, now: str) -> None:
    """Crée la fiche 'pending' d'une avance de frais pour une transaction.

    No-op si payer_contact_id est None ou si le contact n'existe plus
    (FK OFF : on ne crée pas de fiche fantôme sans bénéficiaire identifiable).
    Le montant suivi est le montant absolu de la transaction.
    """
    if payer_contact_id is None:
        return
    try:
        contact = conn.execute(
            "SELECT name FROM contacts WHERE id = ?", (payer_contact_id,)
        ).fetchone()
        if contact is None:
            return
        tx = conn.execute(
            "SELECT amount FROM transactions WHERE id = ?", (tx_id,)
        ).fetchone()
        amount = abs(tx[0]) if tx else 0
        conn.execute(
            """INSERT INTO reimbursements
               (transaction_id, contact_id, person_name, amount, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (tx_id, payer_contact_id, contact[0], amount, now, now),
        )
    except sqlite3.OperationalError:
        pass


def delete_advance(conn, tx_id: int) -> None:
    """Supprime la fiche d'avance liée à une transaction (payeur retiré ou
    transaction supprimée). Les écritures de décaissement déjà générées
    (reimbursement_transaction_id) ne sont pas concernées."""
    try:
        conn.execute("DELETE FROM reimbursements WHERE transaction_id = ?", (tx_id,))
    except sqlite3.OperationalError:
        pass


def sync_pending_advance_amount(conn, tx_id: int, now: str) -> None:
    """Aligne le montant d'une avance encore 'pending' sur celui de la
    transaction (édition du montant sans changement de payeur). Une avance
    déjà réglée n'est jamais retouchée."""
    try:
        tx = conn.execute(
            "SELECT amount FROM transactions WHERE id = ?", (tx_id,)
        ).fetchone()
        if tx is None:
            return
        conn.execute(
            "UPDATE reimbursements SET amount = ?, updated_at = ? "
            "WHERE transaction_id = ? AND status = 'pending'",
            (abs(tx[0]), now, tx_id),
        )
    except sqlite3.OperationalError:
        pass
