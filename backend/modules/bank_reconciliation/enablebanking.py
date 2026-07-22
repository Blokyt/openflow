"""Connecteur Enable Banking (agrégation bancaire PSD2, lecture seule).

Enable Banking est un AISP régulé : aucune donnée n'est récupérée par scraping.
Le tier gratuit « Restricted Production » permet de connecter ses propres comptes
(cas d'usage de l'association) sans contrat ni KYB. Auth par JWT RS256 signé avec
une clé privée RSA ; l'Application ID (obtenu au Control Panel après upload du
certificat public) sert de `kid`.

Flux : start_auth (redirection SCA vers la banque) -> la banque redirige vers
redirect_url avec ?code=...&state=... -> create_session(code) -> comptes + uid
-> get_transactions(uid). Consentement valable ~90 jours (re-SCA ensuite).
"""
import time

import httpx
import jwt

from backend.modules.bank_reconciliation.parsers import _amount_to_cents, _assign_external_ids

API_BASE = "https://api.enablebanking.com"


class EnableBankingError(Exception):
    pass


class EnableBankingClient:
    def __init__(self, application_id: str, private_key: str, http=None):
        self.application_id = application_id
        self.private_key = private_key
        self._http = http or httpx.Client(timeout=30.0)

    # -- Authentification ----------------------------------------------------

    def _jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,  # <= 24 h autorisé par l'API
        }
        try:
            token = jwt.encode(
                payload, self.private_key, algorithm="RS256",
                headers={"typ": "JWT", "kid": self.application_id},
            )
        except Exception as e:
            raise EnableBankingError(f"Clé privée Enable Banking invalide : {e}")
        # PyJWT >= 2 renvoie une str ; on garantit le type.
        return token if isinstance(token, str) else token.decode("utf-8")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self._http.request(
                method, f"{API_BASE}{path}",
                headers={"Authorization": f"Bearer {self._jwt()}"},
                **kwargs,
            )
        except httpx.RequestError as e:
            raise EnableBankingError(f"Connexion à Enable Banking impossible : {e}")
        if resp.status_code == 401:
            raise EnableBankingError(
                "Authentification Enable Banking refusée (401) : vérifie l'Application ID et la clé privée."
            )
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                detail = body.get("message") or body.get("error") or str(body)
            except ValueError:
                detail = resp.text[:200]
            raise EnableBankingError(f"Erreur Enable Banking ({resp.status_code}) : {detail}")
        try:
            return resp.json()
        except ValueError:
            raise EnableBankingError("Réponse Enable Banking illisible")

    # -- Endpoints -----------------------------------------------------------

    def get_aspsps(self, country: str = "FR") -> list:
        data = self._request("GET", "/aspsps", params={"country": country})
        return data.get("aspsps", data.get("data", []))

    def start_auth(self, aspsp_name: str, aspsp_country: str, redirect_url: str,
                   state: str, valid_until: str, psu_type: str = "business") -> dict:
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": aspsp_name, "country": aspsp_country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": psu_type,
        }
        return self._request("POST", "/auth", json=body)

    def create_session(self, code: str) -> dict:
        return self._request("POST", "/sessions", json={"code": code})

    def get_transactions(self, account_uid: str, date_from: str | None = None) -> list:
        results: list = []
        params: dict = {}
        if date_from:
            params["date_from"] = date_from
        while True:
            data = self._request("GET", f"/accounts/{account_uid}/transactions", params=params)
            results.extend(data.get("transactions", []))
            cont = data.get("continuation_key")
            if not cont:
                break
            params = dict(params, continuation_key=cont)
        return results


def generate_keypair_and_cert() -> tuple[str, str]:
    """Génère une paire RSA 2048 + un certificat auto-signé (PEM).

    C'est exactement ce qu'Enable Banking attend : la clé privée signe les JWT,
    le certificat public (qui contient la clé publique) est enregistré côté
    Enable Banking pour vérifier les signatures. Évite à l'utilisateur d'avoir
    à manipuler openssl. Renvoie (private_key_pem, certificate_pem).
    """
    from datetime import datetime, timezone, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "openflow")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return private_pem, cert_pem


def normalize_transactions(raw: list) -> list:
    """Convertit les transactions Enable Banking vers le format interne
    (mêmes clés que les parseurs CSV/OFX). credit_debit_indicator donne le
    signe ; le montant est une chaîne décimale (« 1.23 »)."""
    rows = []
    for t in raw:
        amt = t.get("transaction_amount") or {}
        cents = _amount_to_cents(str(amt.get("amount", "0")))
        if t.get("credit_debit_indicator") == "DBIT":
            cents = -abs(cents)
        else:
            cents = abs(cents)
        ref = t.get("entry_reference") or t.get("transaction_id") or ""
        rinfo = t.get("remittance_information") or []
        label = " ".join(str(x) for x in rinfo).strip() if rinfo else ""
        creditor = (t.get("creditor") or {}).get("name") or ""
        debtor = (t.get("debtor") or {}).get("name") or ""
        counterparty = (debtor if cents >= 0 else creditor) or creditor or debtor or ""
        if not label:
            label = counterparty or "Opération"
        rows.append({
            "external_id": f"eb:{ref}" if ref else "",
            "booking_date": t.get("booking_date") or t.get("value_date") or "",
            "amount": cents,
            "currency": amt.get("currency", "EUR"),
            "label": label,
            "counterparty": counterparty,
        })
    return _assign_external_ids(rows)
