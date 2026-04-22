import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest

def test_list_categories(client):
    response = client.get("/api/categories/")
    assert response.status_code == 200

def test_create_category(client):
    response = client.post("/api/categories/", json={"name": "Communication", "color": "#3B82F6"})
    assert response.status_code == 201
    assert response.json()["name"] == "Communication"

def test_create_subcategory(client):
    parent = client.post("/api/categories/", json={"name": "Parent"}).json()
    child = client.post("/api/categories/", json={"name": "Child", "parent_id": parent["id"]}).json()
    assert child["parent_id"] == parent["id"]

def test_update_category(client):
    cat = client.post("/api/categories/", json={"name": "Old"}).json()
    response = client.put(f"/api/categories/{cat['id']}", json={"name": "New"})
    assert response.status_code == 200
    assert response.json()["name"] == "New"

def test_delete_category(client):
    cat = client.post("/api/categories/", json={"name": "Del"}).json()
    response = client.delete(f"/api/categories/{cat['id']}")
    assert response.status_code == 200
    assert client.get(f"/api/categories/{cat['id']}").status_code == 404

def test_get_tree(client):
    response = client.get("/api/categories/tree")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_tree_counts_and_totals(client_and_db):
    """Tree nodes expose tx_count, tx_total, descendant_tx_count, descendant_tx_total."""
    client, db_path = client_and_db

    # Create category A with children B and C
    cat_a = client.post("/api/categories/", json={"name": "A"}).json()
    cat_b = client.post("/api/categories/", json={"name": "B", "parent_id": cat_a["id"]}).json()
    cat_c = client.post("/api/categories/", json={"name": "C", "parent_id": cat_a["id"]}).json()

    # 2 transactions on B (amounts 10 and 20)
    client.post("/api/transactions/", json={"date": "2024-01-01", "label": "tx1", "amount": 10, "category_id": cat_b["id"]})
    client.post("/api/transactions/", json={"date": "2024-01-02", "label": "tx2", "amount": 20, "category_id": cat_b["id"]})
    # 1 transaction on C (amount 100)
    client.post("/api/transactions/", json={"date": "2024-01-03", "label": "tx3", "amount": 100, "category_id": cat_c["id"]})

    tree = client.get("/api/categories/tree").json()

    # Helper to find a node by id in tree (recursive)
    def find_node(nodes, node_id):
        for n in nodes:
            if n["id"] == node_id:
                return n
            found = find_node(n.get("children", []), node_id)
            if found:
                return found
        return None

    node_a = find_node(tree, cat_a["id"])
    node_b = find_node(tree, cat_b["id"])
    node_c = find_node(tree, cat_c["id"])

    assert node_a is not None
    assert node_b is not None
    assert node_c is not None

    # A has no direct transactions
    assert node_a["tx_count"] == 0
    assert node_a["tx_total"] == 0.0
    # A descendants: B(2) + C(1) = 3 transactions, 10+20+100 = 130
    assert node_a["descendant_tx_count"] == 3
    assert node_a["descendant_tx_total"] == pytest.approx(130.0)

    # B: 2 transactions, total 30
    assert node_b["tx_count"] == 2
    assert node_b["tx_total"] == pytest.approx(30.0)
    assert node_b["descendant_tx_count"] == 2
    assert node_b["descendant_tx_total"] == pytest.approx(30.0)

    # C: 1 transaction, total 100
    assert node_c["tx_count"] == 1
    assert node_c["tx_total"] == pytest.approx(100.0)
    assert node_c["descendant_tx_count"] == 1
    assert node_c["descendant_tx_total"] == pytest.approx(100.0)
