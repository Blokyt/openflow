"""Tests — module DirENS (export Excel, lignes = catégories, aucun mapping)."""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from openpyxl import load_workbook


def _fy(client, name="2025-2026", start="2025-09-01"):
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start})
    assert r.status_code == 201, r.text
    return r.json()


def _cat(client, name):
    return client.post("/api/categories/", json={"name": name}).json()


def _internal(client, name):
    return client.post("/api/entities/", json={"name": name, "type": "internal"}).json()


def _external(client, name="Fournisseur"):
    return client.post("/api/entities/", json={"name": name, "type": "external"}).json()


def _row_with_label(ws, label, max_row=60):
    """Numéro de ligne dont la colonne A vaut `label` (None si absente)."""
    for r in range(1, max_row + 1):
        if ws.cell(row=r, column=1).value == label:
            return r
    return None


# ─── Export : structure ───────────────────────────────────────────────────

def test_export_returns_xlsx(client):
    fy = _fy(client)
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]


def test_export_is_valid_workbook_three_sheets(client):
    fy = _fy(client)
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    wb = load_workbook(io.BytesIO(r.content))
    assert len(wb.sheetnames) == 3


def test_export_writes_club_names_row5(client):
    _internal(client, "GastronomINE")
    fy = _fy(client)
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.worksheets[0]
    row5 = [ws.cell(row=5, column=c).value for c in range(2, 7)]
    assert "GastronomINE" in row5


def test_export_assoc_name_written(client):
    fy = _fy(client)
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}&assoc_name=Mon%20Asso")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.worksheets[0]["A3"].value == "Mon Asso"


def test_export_unknown_fy_returns_404(client):
    r = client.get("/api/direns/export?bilan_fiscal_year_id=9999")
    assert r.status_code == 404, r.text


# ─── Export : lignes = catégories ──────────────────────────────────────────

def test_expense_category_appears_as_row(client):
    ext = _external(client)
    club = _internal(client, "Club")
    cat = _cat(client, "Nourriture")
    fy = _fy(client)
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "Repas", "amount": 5000,  # 50 €
        "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": cat["id"],
    })
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.worksheets[0]
    row = _row_with_label(ws, "Nourriture")
    assert row is not None, "la catégorie devrait apparaître en ligne"
    assert ws.cell(row=row, column=2).value == 50.0  # colonne B = premier club


def test_two_categories_two_rows(client):
    ext = _external(client)
    club = _internal(client, "Club")
    c1 = _cat(client, "Nourriture")
    c2 = _cat(client, "Transport")
    fy = _fy(client)
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "Repas", "amount": 5000,
        "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": c1["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2025-10-02", "label": "Train", "amount": 3000,
        "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": c2["id"],
    })
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    assert ws.cell(row=_row_with_label(ws, "Nourriture"), column=2).value == 50.0
    assert ws.cell(row=_row_with_label(ws, "Transport"), column=2).value == 30.0


def test_uncategorized_expense_grouped(client):
    ext = _external(client)
    club = _internal(client, "Club")
    fy = _fy(client)
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "Sans cat", "amount": 1200,
        "from_entity_id": club["id"], "to_entity_id": ext["id"],
    })
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    row = _row_with_label(ws, "Non catégorisé")
    assert row is not None
    assert ws.cell(row=row, column=2).value == 12.0


def test_income_category_in_financing_section(client):
    ext = _external(client)
    club = _internal(client, "Club")
    cat = _cat(client, "Subventions")
    fy = _fy(client)
    # Recette : from externe -> to club
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "Subvention", "amount": 20000,  # 200 €
        "from_entity_id": ext["id"], "to_entity_id": club["id"], "category_id": cat["id"],
    })
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    row = _row_with_label(ws, "Subventions")
    assert row is not None
    assert ws.cell(row=row, column=2).value == 200.0


def test_total_label_present(client):
    ext = _external(client)
    club = _internal(client, "Club")
    cat = _cat(client, "Nourriture")
    fy = _fy(client)
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "Repas", "amount": 5000,
        "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": cat["id"],
    })
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    assert _row_with_label(ws, "TOTAL DEPENSES REELLES") is not None


def test_budget_sheet_category_row(client):
    club = _internal(client, "Club")
    cat = _cat(client, "Matériel")
    fy = _fy(client)
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": club["id"], "category_id": cat["id"], "direction": "expense", "amount": 25000,  # 250 €
    })
    r = client.get(
        f"/api/direns/export?bilan_fiscal_year_id={fy['id']}&budget_fiscal_year_id={fy['id']}"
    )
    ws2 = load_workbook(io.BytesIO(r.content)).worksheets[1]
    row = _row_with_label(ws2, "Matériel")
    assert row is not None
    assert ws2.cell(row=row, column=2).value == 250.0


def test_many_categories_expand_rows(client):
    """Plus de 26 catégories : le bloc s'agrandit, toutes les lignes présentes."""
    ext = _external(client)
    club = _internal(client, "Club")
    fy = _fy(client)
    names = [f"Categorie {i:02d}" for i in range(30)]
    for i, nm in enumerate(names):
        c = _cat(client, nm)
        client.post("/api/transactions/", json={
            "date": "2025-10-01", "label": nm, "amount": 100 * (i + 1),
            "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": c["id"],
        })
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    for nm in names:
        assert _row_with_label(ws, nm) is not None, f"{nm} manquante"
    # Le total reste cohérent (présent sous les catégories).
    assert _row_with_label(ws, "TOTAL DEPENSES REELLES") is not None
