"""Coherence tests: categories."""
import pytest


# ============================================================
# CATEGORIES — tree coherence
# ============================================================

def test_categories_tree_parent_child(client):
    """Category tree must show correct parent-child hierarchy."""
    parent = client.post("/api/categories/", json={
        "name": "Depenses", "color": "#f00", "icon": "folder", "position": 1,
    }).json()
    child = client.post("/api/categories/", json={
        "name": "Fournitures", "color": "#0f0", "icon": "box",
        "position": 2, "parent_id": parent["id"],
    }).json()

    tree = client.get("/api/categories/tree").json()
    parent_node = next((n for n in tree if n["id"] == parent["id"]), None)
    assert parent_node is not None
    assert len(parent_node["children"]) == 1
    assert parent_node["children"][0]["id"] == child["id"]


def test_categories_tree_orphan_at_root(client):
    """Category with non-existent parent_id should appear at root level."""
    cat = client.post("/api/categories/", json={
        "name": "Orphelin", "color": "#000", "icon": "x",
        "position": 1, "parent_id": 99999,
    }).json()

    tree = client.get("/api/categories/tree").json()
    root_ids = [n["id"] for n in tree]
    assert cat["id"] in root_ids
