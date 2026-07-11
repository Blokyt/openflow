"""Courses concurrentes sur le workflow soumissions et le budget.

Deux clients admin distincts (donc deux connexions SQLite) sont lancés en
parallèle sur la même ressource. Un threading.Barrier injecté sur un hook
appelé APRÈS le contrôle de statut et AVANT l'écriture force les deux requêtes
à avoir toutes les deux lu l'état « pending » avant qu'aucune n'écrive : c'est
la fenêtre de course réelle. Sans garde CAS, on obtient une double transaction
comptable (ou une transaction postée malgré un refus). Avec la garde, une seule
écriture gagne, l'autre reçoit 409.
"""
import sqlite3
import threading

import backend.modules.budget.api as budget_api
import backend.modules.submissions.api as sub_api

FIXED_NOW = "2025-03-01T12:00:00+00:00"


def _create_entity(client, name, type_):
    r = client.post("/api/entities/", json={"name": name, "type": type_})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_pending_submission(client):
    internal = _create_entity(client, "Club", "internal")
    external = _create_entity(client, "Fournisseur", "external")
    r = client.post("/api/submissions/", json={
        "date": "2025-03-01", "label": "Achat", "amount": 4550,
        "entity_id": internal, "counterparty_entity_id": external, "direction": "expense",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _run_parallel(fn_a, fn_b):
    results = {}

    def _wrap(name, fn):
        results[name] = fn()

    ta = threading.Thread(target=_wrap, args=("a", fn_a))
    tb = threading.Thread(target=_wrap, args=("b", fn_b))
    ta.start(); tb.start(); ta.join(); tb.join()
    return results


def test_concurrent_double_approve_creates_single_transaction(client_and_db, login_as, monkeypatch):
    setup, db_path = client_and_db
    sid = _create_pending_submission(setup)

    barrier = threading.Barrier(2)

    def _sync(conn, date):
        barrier.wait(timeout=5)
        return False

    monkeypatch.setattr(sub_api, "_date_in_closed_period", _sync)

    admin_a = login_as("admin.a@test.local", is_admin=True)
    admin_b = login_as("admin.b@test.local", is_admin=True)
    results = _run_parallel(
        lambda: admin_a.post(f"/api/submissions/{sid}/approve").status_code,
        lambda: admin_b.post(f"/api/submissions/{sid}/approve").status_code,
    )

    assert sorted(results.values()) == [200, 409], \
        f"une seule approbation doit réussir, obtenu {sorted(results.values())}"
    conn = sqlite3.connect(str(db_path))
    try:
        tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        status = conn.execute(
            "SELECT status FROM transaction_submissions WHERE id = ?", (sid,)).fetchone()[0]
    finally:
        conn.close()
    assert tx_count == 1, f"exactement une transaction comptable attendue, obtenu {tx_count}"
    assert status == "approved"


def test_concurrent_approve_vs_reject_stays_coherent(client_and_db, login_as, monkeypatch):
    setup, db_path = client_and_db
    sid = _create_pending_submission(setup)

    barrier = threading.Barrier(2)

    def _sync_now():
        barrier.wait(timeout=5)
        return FIXED_NOW

    monkeypatch.setattr(sub_api, "_now", _sync_now)

    admin_a = login_as("admin.a@test.local", is_admin=True)
    admin_b = login_as("admin.b@test.local", is_admin=True)
    results = _run_parallel(
        lambda: admin_a.post(f"/api/submissions/{sid}/approve").status_code,
        lambda: admin_b.post(f"/api/submissions/{sid}/reject", json={"comment": "doublon"}).status_code,
    )

    assert sorted(results.values()) == [200, 409], \
        f"une seule décision doit aboutir, obtenu {sorted(results.values())}"
    conn = sqlite3.connect(str(db_path))
    try:
        tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        status = conn.execute(
            "SELECT status FROM transaction_submissions WHERE id = ?", (sid,)).fetchone()[0]
    finally:
        conn.close()
    # Invariant dur : une transaction est postée SI ET SEULEMENT SI le statut final
    # est 'approved'. Un refus ne doit jamais laisser d'argent comptabilisé.
    if status == "rejected":
        assert tx_count == 0, "aucune transaction ne doit exister si la soumission est refusée"
    else:
        assert status == "approved"
        assert tx_count == 1, "une transaction et une seule si la soumission est approuvée"


def test_concurrent_identical_allocations_never_500(client_and_db, login_as, monkeypatch):
    setup, db_path = client_and_db
    entity = _create_entity(setup, "Club", "internal")
    r = setup.post("/api/budget/fiscal-years", json={"name": "Exercice 2025", "start_date": "2025-01-01"})
    assert r.status_code == 201, r.text
    fy_id = r.json()["id"]

    barrier = threading.Barrier(2)

    def _sync_now():
        barrier.wait(timeout=5)
        return FIXED_NOW

    monkeypatch.setattr(budget_api, "_now", _sync_now)

    payload = {"entity_id": entity, "category_id": None, "direction": "expense", "amount": 100000}
    admin_a = login_as("admin.a@test.local", is_admin=True)
    admin_b = login_as("admin.b@test.local", is_admin=True)
    results = _run_parallel(
        lambda: admin_a.post(f"/api/budget/fiscal-years/{fy_id}/allocations", json=payload).status_code,
        lambda: admin_b.post(f"/api/budget/fiscal-years/{fy_id}/allocations", json=payload).status_code,
    )

    assert 500 not in results.values(), f"aucune 500 sous concurrence, obtenu {results.values()}"
    assert sorted(results.values()) == [201, 409], \
        f"une création réussit, l'autre est un doublon propre (409), obtenu {sorted(results.values())}"
    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM budget_allocations WHERE fiscal_year_id = ?", (fy_id,)).fetchone()[0]
    finally:
        conn.close()
    assert count == 1, f"une seule allocation doit subsister, obtenu {count}"
