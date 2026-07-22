"""Tests de l'API de rapprochement bancaire.

Modèle : chaque ligne bancaire (bank_transactions, montant SIGNÉ) est associée
à une ou plusieurs écritures (transactions, montant positif) via une liaison
many-to-many. Une ligne est rapprochée quand SUM(écritures) == ABS(montant), ou
si marquée manuellement.
"""
import sqlite3


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _entities(client):
    interne = client.post("/api/entities/", json={"name": "Asso", "type": "internal"}).json()["id"]
    externe = client.post("/api/entities/", json={"name": "Tiers", "type": "external"}).json()["id"]
    return interne, externe


def _recette(client, interne, externe, amount, date="2026-01-15", label="recette"):
    return client.post("/api/transactions/", json={
        "date": date, "label": label, "amount": amount,
        "from_entity_id": externe, "to_entity_id": interne,
    }).json()["id"]


def _depense(client, interne, externe, amount, date="2026-01-15", label="depense"):
    return client.post("/api/transactions/", json={
        "date": date, "label": label, "amount": amount,
        "from_entity_id": interne, "to_entity_id": externe,
    }).json()["id"]


def _make_account(client, interne):
    r = client.post("/api/bank_reconciliation/accounts", json={"entity_id": interne, "label": "CE Pro"})
    assert r.status_code == 201
    return r.json()["id"]


def _seed_bank_tx(db_path, account_id, amount, external_id, date="2026-01-15", label="ligne"):
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        """INSERT INTO bank_transactions
           (bank_account_id, external_id, booking_date, amount, currency, label, counterparty, reconciled_manual, imported_at)
           VALUES (?, ?, ?, ?, 'EUR', ?, '', 0, '2026-01-20T00:00:00')""",
        (account_id, external_id, date, amount, label),
    )
    conn.commit()
    bid = cur.lastrowid
    conn.close()
    return bid


def _tx_reconciled(db_path, tx_id):
    conn = sqlite3.connect(db_path)
    val = conn.execute("SELECT reconciled FROM transactions WHERE id = ?", (tx_id,)).fetchone()[0]
    conn.close()
    return val


# ─── Comptes ──────────────────────────────────────────────────────────────────

def test_create_account_requires_internal_entity(client_and_db):
    client, _ = client_and_db
    _, externe = _entities(client)
    r = client.post("/api/bank_reconciliation/accounts", json={"entity_id": externe, "label": "X"})
    assert r.status_code == 400


def test_create_account_unknown_entity_404(client_and_db):
    client, _ = client_and_db
    r = client.post("/api/bank_reconciliation/accounts", json={"entity_id": 99999, "label": "X"})
    assert r.status_code == 404


def test_list_accounts_counters(client_and_db):
    client, db_path = client_and_db
    interne, _ = _entities(client)
    acc = _make_account(client, interne)
    _seed_bank_tx(db_path, acc, 100000, "e1")
    _seed_bank_tx(db_path, acc, -5000, "e2")
    accs = client.get("/api/bank_reconciliation/accounts").json()
    assert len(accs) == 1
    assert accs[0]["tx_count"] == 2
    assert accs[0]["to_reconcile_count"] == 2


# ─── Import (idempotence) ─────────────────────────────────────────────────────

CSV = "Date;Libellé;Débit;Crédit\n15/01/2026;VIR CLIENT;;1 250,00\n16/01/2026;ACHAT;45,90;\n"


def test_import_then_reimport_is_idempotent(client_and_db):
    client, _ = client_and_db
    interne, _ = _entities(client)
    acc = _make_account(client, interne)

    r1 = client.post(f"/api/bank_reconciliation/accounts/{acc}/import",
                     files={"file": ("releve.csv", CSV.encode("utf-8"), "text/csv")})
    assert r1.status_code == 200
    assert r1.json()["imported"] == 2

    r2 = client.post(f"/api/bank_reconciliation/accounts/{acc}/import",
                     files={"file": ("releve.csv", CSV.encode("utf-8"), "text/csv")})
    assert r2.json()["imported"] == 0
    assert r2.json()["skipped"] == 2

    txs = client.get(f"/api/bank_reconciliation/transactions?account_id={acc}&status=all").json()
    assert len(txs) == 2


def test_import_empty_file_400(client_and_db):
    client, _ = client_and_db
    interne, _ = _entities(client)
    acc = _make_account(client, interne)
    r = client.post(f"/api/bank_reconciliation/accounts/{acc}/import",
                    files={"file": ("v.csv", b"", "text/csv")})
    assert r.status_code == 400


def test_import_unknown_account_404(client_and_db):
    client, _ = client_and_db
    r = client.post("/api/bank_reconciliation/accounts/99999/import",
                    files={"file": ("v.csv", CSV.encode("utf-8"), "text/csv")})
    assert r.status_code == 404


# ─── Association : regroupement (N écritures -> 1 ligne) ──────────────────────

def test_group_multiple_entries_reconciles_line(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 125000, "e1")   # crédit 1250 €
    tx1 = _recette(client, interne, externe, 80000)
    tx2 = _recette(client, interne, externe, 45000)

    r = client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx1})
    assert r.status_code == 201
    assert r.json()["reconciled"] is False
    assert r.json()["pending_cents"] == 45000

    r = client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx2})
    body = r.json()
    assert body["linked_cents"] == 125000
    assert body["pending_cents"] == 0
    assert body["reconciled"] is True
    # Les écritures compta passent en rapprochées.
    assert _tx_reconciled(db_path, tx1) == 1
    assert _tx_reconciled(db_path, tx2) == 1


def test_line_moves_to_reconciled_list(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 90000, "e1")
    tx = _recette(client, interne, externe, 90000)
    client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx})

    pending = client.get(f"/api/bank_reconciliation/transactions?account_id={acc}&status=pending").json()
    reconciled = client.get(f"/api/bank_reconciliation/transactions?account_id={acc}&status=reconciled").json()
    assert pending == []
    assert len(reconciled) == 1


# ─── Dissociation ─────────────────────────────────────────────────────────────

def test_unlink_restores_pending_and_flag(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 90000, "e1")
    tx = _recette(client, interne, externe, 90000)
    client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx})
    assert _tx_reconciled(db_path, tx) == 1

    r = client.delete(f"/api/bank_reconciliation/transactions/{bid}/links/{tx}")
    assert r.status_code == 200
    assert r.json()["pending_cents"] == 90000
    assert r.json()["reconciled"] is False
    assert _tx_reconciled(db_path, tx) == 0


# ─── Division : une écriture répartie sur plusieurs lignes (many-to-many) ─────

def test_same_entry_can_link_to_multiple_bank_lines(client_and_db):
    """Aucune exclusivité : une écriture peut être associée à plusieurs lignes
    bancaires (cas d'un mouvement compta réglé en plusieurs fois côté banque)."""
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    b1 = _seed_bank_tx(db_path, acc, 60000, "e1")
    b2 = _seed_bank_tx(db_path, acc, 40000, "e2")
    tx = _recette(client, interne, externe, 100000)

    r1 = client.post(f"/api/bank_reconciliation/transactions/{b1}/links", json={"transaction_id": tx})
    r2 = client.post(f"/api/bank_reconciliation/transactions/{b2}/links", json={"transaction_id": tx})
    assert r1.status_code == 201
    assert r2.status_code == 201  # pas de 409 : contrairement à HelloAsso, pas d'exclusivité


def test_duplicate_link_same_line_conflict(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 90000, "e1")
    tx = _recette(client, interne, externe, 90000)
    client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx})
    r = client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx})
    assert r.status_code == 409


# ─── Marquage manuel ──────────────────────────────────────────────────────────

def test_manual_mark_reconciles_despite_mismatch(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 90000, "e1")
    tx = _recette(client, interne, externe, 70000)   # ne couvre pas tout
    client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx})

    r = client.post(f"/api/bank_reconciliation/transactions/{bid}/mark", json={"reconciled": True})
    assert r.status_code == 200
    assert r.json()["reconciled"] is True
    assert r.json()["reconciled_manual"] is True
    assert r.json()["pending_cents"] == 20000   # l'écart reste visible

    # Annulation du marquage : redevient non rapprochée.
    r = client.post(f"/api/bank_reconciliation/transactions/{bid}/mark", json={"reconciled": False})
    assert r.json()["reconciled"] is False


# ─── Suggestions ──────────────────────────────────────────────────────────────

def test_suggestions_same_sign_sorted_closest_below(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 100000, "e1")   # crédit -> recettes
    _recette(client, interne, externe, 90000, label="r90")
    _recette(client, interne, externe, 50000, label="r50")
    _recette(client, interne, externe, 110000, label="r110")
    _depense(client, interne, externe, 95000, label="d95")   # dépense : mauvais sens

    s = client.get(f"/api/bank_reconciliation/transactions/{bid}/suggestions").json()
    amounts = [x["amount"] for x in s["suggestions"]]
    # reste = 100000 : inférieurs les plus proches (90000, 50000) puis supérieur (110000)
    assert amounts == [90000, 50000, 110000]


def test_suggestions_debit_line_offers_expenses(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, -8000, "e1")   # débit -> dépenses
    dep = _depense(client, interne, externe, 8000, label="edf")
    _recette(client, interne, externe, 8000, label="cotis")   # recette : exclue

    s = client.get(f"/api/bank_reconciliation/transactions/{bid}/suggestions").json()
    ids = [x["transaction_id"] for x in s["suggestions"]]
    assert ids == [dep]


def test_suggestions_exclude_already_linked_to_this_line(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 100000, "e1")
    tx = _recette(client, interne, externe, 90000)
    client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx})

    s = client.get(f"/api/bank_reconciliation/transactions/{bid}/suggestions").json()
    ids = [x["transaction_id"] for x in s["suggestions"]]
    assert tx not in ids
    assert s["pending_cents"] == 10000


# ─── 404 divers ───────────────────────────────────────────────────────────────

def test_links_unknown_line_404(client_and_db):
    client, _ = client_and_db
    r = client.get("/api/bank_reconciliation/transactions/99999/links")
    assert r.status_code == 404


def test_add_link_unknown_transaction_404(client_and_db):
    client, db_path = client_and_db
    interne, _ = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 90000, "e1")
    r = client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": 99999})
    assert r.status_code == 404


def test_list_transactions_unknown_account_404(client_and_db):
    client, _ = client_and_db
    r = client.get("/api/bank_reconciliation/transactions?account_id=99999")
    assert r.status_code == 404


def test_delete_account_cascades_and_unreconciles(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 90000, "e1")
    tx = _recette(client, interne, externe, 90000)
    client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx})

    r = client.delete(f"/api/bank_reconciliation/accounts/{acc}")
    assert r.status_code == 200
    assert _tx_reconciled(db_path, tx) == 0
    # Le compte et ses lignes ont disparu.
    assert client.get("/api/bank_reconciliation/accounts").json() == []


# ─── Statut "rapprochée" des écritures (coche transactions) ───────────────────

def test_reconciled_transaction_excluded_from_other_suggestions(client_and_db):
    """Une écriture déjà rapprochée (liée à une ligne) n'est plus re-proposée."""
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    b1 = _seed_bank_tx(db_path, acc, 90000, "e1")
    b2 = _seed_bank_tx(db_path, acc, 90000, "e2")
    tx = _recette(client, interne, externe, 90000)
    client.post(f"/api/bank_reconciliation/transactions/{b1}/links", json={"transaction_id": tx})
    s = client.get(f"/api/bank_reconciliation/transactions/{b2}/suggestions").json()
    assert tx not in [x["transaction_id"] for x in s["suggestions"]]


def test_manual_reconcile_flag_toggles_and_excludes(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    b1 = _seed_bank_tx(db_path, acc, 90000, "e1")
    tx = _recette(client, interne, externe, 90000)
    r = client.put(f"/api/transactions/{tx}", json={"reconciled_manual": True})
    assert r.json()["reconciled_manual"] == 1
    s = client.get(f"/api/bank_reconciliation/transactions/{b1}/suggestions").json()
    assert tx not in [x["transaction_id"] for x in s["suggestions"]]
    # On peut annuler le forçage.
    r = client.put(f"/api/transactions/{tx}", json={"reconciled_manual": False})
    assert r.json()["reconciled_manual"] == 0


# ─── Imputation partielle (montant par lien) ──────────────────────────────────

def test_partial_allocation_across_entries(client_and_db):
    """Ligne 55 € couverte par une écriture de 25 € + une partie d'une de 90 €.
    La 2e n'impute que 30 € (le restant à couvrir), et garde 60 € pour ailleurs."""
    client, db_path = client_and_db
    interne, externe = _entities(client)
    acc = _make_account(client, interne)
    bid = _seed_bank_tx(db_path, acc, 5500, "e1")          # ligne 55 €
    tx25 = _recette(client, interne, externe, 2500)        # écriture 25 €
    tx90 = _recette(client, interne, externe, 9000)        # écriture 90 €

    r1 = client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx25})
    assert r1.json()["linked_cents"] == 2500
    assert r1.json()["pending_cents"] == 3000

    r2 = client.post(f"/api/bank_reconciliation/transactions/{bid}/links", json={"transaction_id": tx90})
    body = r2.json()
    assert body["linked_cents"] == 5500          # 25 + 30, pas 115
    assert body["pending_cents"] == 0
    assert body["reconciled"] is True
    # Le lien de la 90 € n'impute que 30 €.
    link90 = next(l for l in body["links"] if l["transaction_id"] == tx90)
    assert link90["amount"] == 3000
    assert link90["tx_amount"] == 9000

    # tx90 n'est pas entièrement imputée -> pas rapprochée, et il lui reste 60 €.
    assert _tx_reconciled(db_path, tx90) == 0
    b2 = _seed_bank_tx(db_path, acc, 6000, "e2")
    s = client.get(f"/api/bank_reconciliation/transactions/{b2}/suggestions").json()
    sug90 = next((x for x in s["suggestions"] if x["transaction_id"] == tx90), None)
    assert sug90 is not None
    assert sug90["remaining_cents"] == 6000
