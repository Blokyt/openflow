"""Cohérence transversale de l'ancrage Trésorerie (source de vérité unique).

Vérifie que dashboard, bilan et Trésorerie affichent le MÊME total, que le
bilan reste équilibré dans ce mode, que l'ombrelle agrégée est exclue de la
ventilation, et que le service treasury tient ses cas limites (résiduel sans
sœur, Trésorerie non configurée, repli).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import sqlite3

from backend.core.balance import compute_entity_balance
from backend.modules.treasury.service import (
    entity_own_current_cents,
    residual_balance_cents,
    siblings_total_cents,
    treasury_total_cents,
)


def _make_umbrella(client, db_path):
    umbrella = client.post("/api/entities/", json={
        "name": "BDA global", "type": "internal", "balance_mode": "aggregate"}).json()
    local = client.post("/api/entities/", json={
        "name": "BDA local", "type": "internal", "parent_id": umbrella["id"]}).json()
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE entities SET is_default = 1 WHERE id = ?", (umbrella["id"],))
    conn.execute("UPDATE entities SET is_residual = 1 WHERE id = ?", (local["id"],))
    conn.commit()
    conn.close()
    return umbrella, local


def _set_pocket(client, name, cents, d="2026-06-01"):
    pockets = client.get("/api/treasury/pockets").json()["pockets"]
    p = next(x for x in pockets if x["name"] == name)
    r = client.put(f"/api/treasury/pockets/{p['id']}", json={"reference_cents": cents, "reference_date": d})
    assert r.status_code == 200, r.text


def _conn(db_path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


def test_dashboard_bilan_treasury_all_agree(client_and_db):
    """Global dashboard == total actif du bilan == total Trésorerie, bilan
    équilibré, ombrelle exclue, feuille résiduelle à sa valeur déduite."""
    client, db_path = client_and_db
    umbrella, local = _make_umbrella(client, db_path)
    gastro = client.post("/api/entities/", json={
        "name": "Gastro", "type": "internal", "parent_id": umbrella["id"]}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    client.put(f"/api/entities/{gastro['id']}/balance-ref",
               json={"reference_date": "2026-06-01", "reference_amount": 20000})
    _set_pocket(client, "Compte", 500000)
    _set_pocket(client, "Livret", 200000)  # Trésorerie totale = 700000
    client.post("/api/transactions/", json={
        "date": "2026-06-15", "label": "don", "amount": 10000,
        "from_entity_id": ext["id"], "to_entity_id": local["id"]})
    fy = client.post("/api/budget/fiscal-years",
                     json={"name": "2026", "start_date": "2026-06-01"}).json()

    treasury = client.get("/api/treasury/pockets").json()["total_cents"]
    assert treasury == 700000
    assert client.get("/api/dashboard/summary").json()["balance"] == treasury

    bilan = client.get("/api/reports/bilan", params={"fiscal_year_id": fy["id"]}).json()
    assert bilan["equilibre"] is True
    assert bilan["actif"]["total"] == treasury  # bilan = Trésorerie
    assert bilan["passif"]["total"] == treasury

    names = [d["name"] for d in bilan["actif"]["disponibilites"]]
    assert "BDA global" not in names  # l'ombrelle (contenant) est exclue
    assert "BDA local" in names and "Gastro" in names

    gastro_bal = client.get(f"/api/entities/{gastro['id']}/consolidated").json()["consolidated_balance"]
    local_line = next(d for d in bilan["actif"]["disponibilites"] if d["name"] == "BDA local")
    assert local_line["montant"] == treasury - gastro_bal  # déduit


def test_bilan_instantane_totals_treasury(client_and_db):
    """Le bilan instantané (sans exercice) totalise aussi la Trésorerie."""
    client, db_path = client_and_db
    _make_umbrella(client, db_path)
    _set_pocket(client, "Compte", 420000)
    data = client.get("/api/reports/bilan").json()
    assert data["total_actif"] == 420000
    assert "BDA global" not in [e["name"] for e in data["tresorerie_par_entite"]]


def test_treasury_service_fallback_when_unconfigured(client_and_db):
    """Trésorerie vierge : total None, résiduel None, et entity_own_current_cents
    retombe sur compute_entity_balance (l'agrégée n'est PAS forcée à 0)."""
    client, db_path = client_and_db
    umbrella, local = _make_umbrella(client, db_path)
    conn = _conn(db_path)
    try:
        assert treasury_total_cents(conn) is None
        assert residual_balance_cents(conn, local["id"]) is None
        assert entity_own_current_cents(conn, umbrella["id"]) == \
            compute_entity_balance(conn, umbrella["id"])["balance"]
        assert entity_own_current_cents(conn, local["id"]) == \
            compute_entity_balance(conn, local["id"])["balance"]
    finally:
        conn.close()


def test_treasury_service_residual_without_siblings(client_and_db):
    """Résiduel sans sœur = Trésorerie totale ; ombrelle propre = 0."""
    client, db_path = client_and_db
    umbrella, local = _make_umbrella(client, db_path)
    _set_pocket(client, "Compte", 300000)
    conn = _conn(db_path)
    try:
        assert treasury_total_cents(conn) == 300000
        assert siblings_total_cents(conn, local["id"]) == 0
        assert residual_balance_cents(conn, local["id"]) == 300000
        assert entity_own_current_cents(conn, umbrella["id"]) == 0
        assert entity_own_current_cents(conn, local["id"]) == 300000
    finally:
        conn.close()
