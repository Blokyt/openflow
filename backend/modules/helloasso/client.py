import time

import httpx

TOKEN_URL = "https://api.helloasso.com/oauth2/token"
API_BASE = "https://api.helloasso.com/v5"


class HelloAssoError(Exception):
    pass


def asso_share_cents(payment: dict) -> int:
    """Part revenant à l'association, hors contribution volontaire au site HelloAsso.

    Hypothèse (à confronter à un vrai export) : le découpage est porté par
    payment["items"] ; l'item de type "Contribution" est le pourboire HelloAsso
    et est exclu. Sans items, on retombe sur payment["amount"].
    """
    items = payment.get("items") or []
    if items:
        return sum(int(it.get("amount", 0)) for it in items if it.get("type") != "Contribution")
    return int(payment.get("amount", 0))


class HelloAssoClient:
    def __init__(self, client_id: str, client_secret: str, organization_slug: str, http=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.organization_slug = organization_slug
        self._http = http or httpx.Client(timeout=20.0)
        self._token = None
        self._token_expiry = 0.0

    def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry - 60:
            return self._token
        resp = self._http.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        })
        if resp.status_code != 200:
            raise HelloAssoError(f"Authentification HelloAsso échouée ({resp.status_code})")
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise HelloAssoError("Réponse d'authentification HelloAsso invalide")
        self._token = token
        self._token_expiry = time.monotonic() + int(data.get("expires_in", 1800))
        return self._token

    def _get(self, path: str, params: dict) -> dict:
        token = self._get_token()
        resp = self._http.get(f"{API_BASE}{path}", params=params,
                              headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 403:
            raise HelloAssoError("Accès refusé (403) : vérifie les droits de ta clé API HelloAsso")
        if resp.status_code != 200:
            raise HelloAssoError(f"Erreur API HelloAsso ({resp.status_code})")
        return resp.json()

    def _paginate(self, path: str, base_params: dict) -> list:
        results = []
        params = dict(base_params, pageSize=100)
        while True:
            data = self._get(path, params)
            rows = data.get("data", [])
            results.extend(rows)
            token = (data.get("pagination") or {}).get("continuationToken")
            if not token or not rows:
                break
            params = dict(base_params, pageSize=100, continuationToken=token)
        return results

    def fetch_forms(self) -> list:
        return self._paginate(f"/organizations/{self.organization_slug}/forms", {})

    def fetch_form_payments(self, form_type: str, form_slug: str, start_date: str, end_date: str) -> list:
        path = f"/organizations/{self.organization_slug}/forms/{form_type}/{form_slug}/payments"
        return self._paginate(path, {"from": start_date, "to": end_date})

    def fetch_campaign_totals(self, start_date: str, end_date: str) -> list:
        """Retourne, par campagne, la part asso encaissée sur la période."""
        totals = []
        for form in self.fetch_forms():
            form_type = form.get("formType", "")
            form_slug = form.get("formSlug", "")
            if not form_type or not form_slug:
                continue
            payments = self.fetch_form_payments(form_type, form_slug, start_date, end_date)
            collected = sum(
                asso_share_cents(p) for p in payments if p.get("state") == "Authorized"
            )
            totals.append({
                "form_type": form_type,
                "form_slug": form_slug,
                "title": form.get("title", ""),
                "state": form.get("state", ""),
                "collected_cents": collected,
                "currency": form.get("currency", "EUR"),
            })
        return totals
