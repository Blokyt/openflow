"""Tests du connecteur Enable Banking (Lot 2).

Couvre : signature JWT RS256, normalisation des transactions, configuration
(clé non exposée / conservée), et le flux connect -> finalize -> sync via un
client Enable Banking factice (aucun appel réseau réel)."""
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.modules.bank_reconciliation.enablebanking import (
    EnableBankingClient, booked_balance_cents, normalize_transactions,
)


def test_booked_balance_cents_prefers_clbd():
    balances = [
        {"balance_type": "VALU", "balance_amount": {"amount": "10.00"}},
        {"balance_type": "CLBD", "balance_amount": {"amount": "5874.26"}},
    ]
    assert booked_balance_cents(balances) == 587426
    assert booked_balance_cents([]) is None


def _rsa_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pub


# ─── JWT ──────────────────────────────────────────────────────────────────────

def test_jwt_is_rs256_with_kid_and_claims():
    priv, pub = _rsa_pem()
    client = EnableBankingClient("app-123", priv)
    token = client._jwt()
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == "app-123"
    decoded = jwt.decode(token, pub, algorithms=["RS256"], audience="api.enablebanking.com")
    assert decoded["iss"] == "enablebanking.com"
    assert decoded["exp"] - decoded["iat"] <= 86400


# ─── Normalisation ────────────────────────────────────────────────────────────

def test_normalize_credit_and_debit_signs():
    raw = [
        {"entry_reference": "T1", "transaction_amount": {"amount": "1250.00", "currency": "EUR"},
         "credit_debit_indicator": "CRDT", "booking_date": "2026-03-01",
         "remittance_information": ["VIR CLIENT", "facture 42"]},
        {"entry_reference": "T2", "transaction_amount": {"amount": "45.90", "currency": "EUR"},
         "credit_debit_indicator": "DBIT", "booking_date": "2026-03-02",
         "creditor": {"name": "EDF"}},
    ]
    rows = normalize_transactions(raw)
    assert rows[0]["amount"] == 125000
    assert rows[0]["external_id"] == "eb:T1"
    assert rows[0]["label"] == "VIR CLIENT facture 42"
    assert rows[1]["amount"] == -4590
    assert rows[1]["label"] == "EDF"


def test_normalize_missing_reference_gets_stable_hash():
    raw = [{"transaction_amount": {"amount": "10.00"}, "credit_debit_indicator": "CRDT",
            "booking_date": "2026-03-01", "remittance_information": ["DON"]}]
    rows = normalize_transactions(raw)
    assert rows[0]["external_id"].startswith("csv:")  # hash de secours


# ─── Client factice pour le flux API ──────────────────────────────────────────

class FakeEB:
    def __init__(self, application_id, private_key, http=None):
        self.application_id = application_id

    def get_aspsps(self, country="FR"):
        return [{"name": "Caisse d'Epargne", "country": "FR", "logo": "logo"},
                {"name": "BNP Paribas", "country": "FR"}]

    def start_auth(self, aspsp_name, aspsp_country, redirect_url, state, valid_until, psu_type="business"):
        self.last = {"name": aspsp_name, "redirect_url": redirect_url, "state": state}
        return {"url": "https://auth.enablebanking.com/start?sessionid=abc", "authorization_id": "auth-1"}

    def create_session(self, code):
        return {"session_id": "sess-1", "accounts": [
            {"uid": "uid-1", "account_id": {"iban": "FR7612345678"}, "name": "Compte Pro"},
        ]}

    def get_balances(self, account_uid):
        return [{"balance_type": "CLBD", "balance_amount": {"amount": "1234.56", "currency": "EUR"}}]

    def get_transactions(self, account_uid, date_from=None):
        return [
            {"entry_reference": "T1", "transaction_amount": {"amount": "1250.00", "currency": "EUR"},
             "credit_debit_indicator": "CRDT", "booking_date": "2026-03-01",
             "remittance_information": ["VIR CLIENT"]},
            {"entry_reference": "T2", "transaction_amount": {"amount": "45.90", "currency": "EUR"},
             "credit_debit_indicator": "DBIT", "booking_date": "2026-03-02",
             "creditor": {"name": "EDF"}},
        ]


@pytest.fixture
def fake_eb(monkeypatch):
    monkeypatch.setattr("backend.modules.bank_reconciliation.api.EnableBankingClient", FakeEB)
    return FakeEB


def _configure(client, redirect_url="http://127.0.0.1:8000/bank-reconciliation"):
    r = client.put("/api/bank_reconciliation/config", json={
        "application_id": "app-1", "private_key": "-----BEGIN KEY-----\nx\n-----END KEY-----",
        "redirect_url": redirect_url,
    })
    assert r.status_code == 200


def _make_account(client):
    interne = client.post("/api/entities/", json={"name": "Asso", "type": "internal"}).json()["id"]
    return client.post("/api/bank_reconciliation/accounts", json={"entity_id": interne, "label": "CE"}).json()["id"]


# ─── Config ───────────────────────────────────────────────────────────────────

def test_config_default_not_configured(client):
    r = client.get("/api/bank_reconciliation/config")
    assert r.status_code == 200
    assert r.json()["configured"] is False
    assert r.json()["has_key"] is False


def test_config_put_then_get_hides_key(client):
    _configure(client)
    r = client.get("/api/bank_reconciliation/config").json()
    assert r["configured"] is True
    assert r["has_key"] is True
    assert "private_key" not in r          # la clé n'est jamais réexposée
    assert r["application_id"] == "app-1"


def test_config_empty_key_preserves_existing(client):
    _configure(client)
    # Mise à jour de l'URL sans re-saisir la clé.
    client.put("/api/bank_reconciliation/config", json={
        "application_id": "app-1", "private_key": "", "redirect_url": "http://x/cb",
    })
    r = client.get("/api/bank_reconciliation/config").json()
    assert r["has_key"] is True
    assert r["redirect_url"] == "http://x/cb"


def test_generate_key_produces_cert_and_stores_private_key(client):
    r = client.post("/api/bank_reconciliation/config/generate-key")
    assert r.status_code == 200
    body = r.json()
    assert "BEGIN CERTIFICATE" in body["certificate"]
    assert body["redirect_url"].startswith("https://")

    cfg = client.get("/api/bank_reconciliation/config").json()
    assert cfg["has_key"] is True                 # clé privée stockée
    assert cfg["configured"] is False             # pas encore d'Application ID
    assert "BEGIN CERTIFICATE" in cfg["certificate"]
    assert "private_key" not in cfg               # jamais exposée


def test_generate_then_set_app_id_completes_config(client):
    client.post("/api/bank_reconciliation/config/generate-key")
    # On finit avec l'Application ID (clé vide -> on conserve celle générée).
    client.put("/api/bank_reconciliation/config", json={
        "application_id": "app-xyz", "private_key": "", "redirect_url": "https://127.0.0.1:8000/bank-reconciliation",
    })
    cfg = client.get("/api/bank_reconciliation/config").json()
    assert cfg["configured"] is True
    assert cfg["application_id"] == "app-xyz"


def test_generate_key_resets_application_id(client):
    _configure(client)                            # app-1 configurée
    client.post("/api/bank_reconciliation/config/generate-key")
    cfg = client.get("/api/bank_reconciliation/config").json()
    # Nouvelle clé -> nouvel enregistrement requis : l'Application ID est purgé.
    assert cfg["application_id"] == ""
    assert cfg["configured"] is False
    assert cfg["has_key"] is True


# ─── Banques / connect ────────────────────────────────────────────────────────

def test_banks_requires_config(client):
    r = client.get("/api/bank_reconciliation/banks")
    assert r.status_code == 400


def test_banks_list(client, fake_eb):
    _configure(client)
    r = client.get("/api/bank_reconciliation/banks")
    assert r.status_code == 200
    names = [b["name"] for b in r.json()]
    assert "Caisse d'Epargne" in names


def test_connect_returns_auth_url(client, fake_eb):
    _configure(client)
    acc = _make_account(client)
    r = client.post(f"/api/bank_reconciliation/accounts/{acc}/connect",
                    json={"aspsp_name": "Caisse d'Epargne", "aspsp_country": "FR"})
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://auth.enablebanking.com")
    assert r.json()["state"].startswith(f"{acc}.")


def test_connect_without_redirect_url_400(client, fake_eb):
    client.put("/api/bank_reconciliation/config", json={
        "application_id": "app-1", "private_key": "k", "redirect_url": "",
    })
    acc = _make_account(client)
    r = client.post(f"/api/bank_reconciliation/accounts/{acc}/connect",
                    json={"aspsp_name": "Caisse d'Epargne"})
    assert r.status_code == 400


# ─── Finalize / sync ──────────────────────────────────────────────────────────

def test_finalize_attaches_remote_account(client_and_db, fake_eb):
    client, _ = client_and_db
    _configure(client)
    acc = _make_account(client)
    r = client.post(f"/api/bank_reconciliation/accounts/{acc}/finalize", json={"code": "auth-code"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "enablebanking"
    assert body["eb_account_id"] == "uid-1"
    assert body["iban"] == "FR7612345678"


def test_sync_requires_connected_account(client, fake_eb):
    _configure(client)
    acc = _make_account(client)   # source 'file', pas connecté
    r = client.post(f"/api/bank_reconciliation/accounts/{acc}/sync")
    assert r.status_code == 400


def test_sync_imports_and_is_idempotent(client, fake_eb):
    _configure(client)
    acc = _make_account(client)
    client.post(f"/api/bank_reconciliation/accounts/{acc}/finalize", json={"code": "auth-code"})

    r1 = client.post(f"/api/bank_reconciliation/accounts/{acc}/sync")
    assert r1.status_code == 200
    assert r1.json()["imported"] == 2

    r2 = client.post(f"/api/bank_reconciliation/accounts/{acc}/sync")
    assert r2.json()["imported"] == 0
    assert r2.json()["skipped"] == 2

    txs = client.get(f"/api/bank_reconciliation/transactions?account_id={acc}&status=all").json()
    assert len(txs) == 2
    amounts = sorted(t["amount"] for t in txs)
    assert amounts == [-4590, 125000]

    # La synchro stocke aussi le solde du compte (bonus).
    accs = client.get("/api/bank_reconciliation/accounts").json()
    assert accs[0]["balance_cents"] == 123456
