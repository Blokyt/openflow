"""Tests — module DirENS (mapping catégorie -> ligne + export Excel pré-rempli)."""
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


# ─── Mapping ────────────────────────────────────────────────────────────────

def test_put_line_map_valid(client):
    cat = _cat(client, "Nourriture")
    r = client.put("/api/direns/line-map", json={"category_id": cat["id"], "direns_row": 8})
    assert r.status_code == 200, r.text
    assert r.json()["direns_row"] == 8


def test_put_line_map_title_row_rejected(client):
    cat = _cat(client, "X")
    r = client.put("/api/direns/line-map", json={"category_id": cat["id"], "direns_row": 7})
    assert r.status_code == 400, r.text


def test_put_line_map_section_mismatch_rejected(client):
    cat = _cat(client, "Sub")
    r = client.put(
        "/api/direns/line-map",
        json={"category_id": cat["id"], "direns_row": 35, "section": "expense"},
    )
    assert r.status_code == 400, r.text


def test_get_line_map_lists_unmapped_and_catalog(client):
    cat = _cat(client, "Boissons")
    data = client.get("/api/direns/line-map").json()
    assert any(c["category_id"] == cat["id"] for c in data["unmapped"])
    assert len(data["rows"]) >= 4  # au moins les groupes Achats/Services/Prestataires/Clubs/Financements


def test_delete_line_map(client):
    cat = _cat(client, "Matériel")
    client.put("/api/direns/line-map", json={"category_id": cat["id"], "direns_row": 11})
    r = client.delete(f"/api/direns/line-map/{cat['id']}")
    assert r.status_code == 200, r.text
    data = client.get("/api/direns/line-map").json()
    assert all(m["category_id"] != cat["id"] for m in data["mapping"])


# ─── Export ─────────────────────────────────────────────────────────────────

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


def test_export_expense_value_in_mapped_cell(client):
    ext = _external(client)
    club = _internal(client, "Club")
    cat = _cat(client, "Nourriture")
    client.put("/api/direns/line-map", json={"category_id": cat["id"], "direns_row": 8})
    fy = _fy(client)
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "Repas", "amount": 5000,  # 50 €
        "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": cat["id"],
    })
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.worksheets[0]
    assert ws["B8"].value == 50.0


def test_export_respects_mapping_row(client):
    ext = _external(client)
    club = _internal(client, "Club")
    cat = _cat(client, "Hébergement")
    client.put("/api/direns/line-map", json={"category_id": cat["id"], "direns_row": 15})
    fy = _fy(client)
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "Hotel", "amount": 10000,  # 100 €
        "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": cat["id"],
    })
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}")
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.worksheets[0]
    assert ws["B15"].value == 100.0
    assert ws["B8"].value in (None, 0)


def test_export_budget_sheet_from_allocations(client):
    club = _internal(client, "Club")
    cat = _cat(client, "Matériel")
    client.put("/api/direns/line-map", json={"category_id": cat["id"], "direns_row": 11})
    fy = _fy(client)
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": club["id"], "category_id": cat["id"], "direction": "expense", "amount": 25000,  # 250 €
    })
    r = client.get(
        f"/api/direns/export?bilan_fiscal_year_id={fy['id']}&budget_fiscal_year_id={fy['id']}"
    )
    wb = load_workbook(io.BytesIO(r.content))
    ws2 = wb.worksheets[1]
    assert ws2["B11"].value == 250.0


def test_export_assoc_name_written(client):
    fy = _fy(client)
    r = client.get(f"/api/direns/export?bilan_fiscal_year_id={fy['id']}&assoc_name=Mon%20Asso")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.worksheets[0]["A3"].value == "Mon Asso"


def test_export_unknown_fy_returns_404(client):
    r = client.get("/api/direns/export?bilan_fiscal_year_id=9999")
    assert r.status_code == 404, r.text
