import pytest

from backend.modules.helloasso.client import HelloAssoClient, asso_share_cents, HelloAssoError


class FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttp:
    """Faux client httpx : .post pour le token, .get pour l'API (réponses séquencées)."""
    def __init__(self, token_resp, get_responses):
        self.token_resp = token_resp
        self.get_responses = list(get_responses)
        self.calls = []

    def post(self, url, data=None, **kw):
        self.calls.append(("POST", url, data))
        return self.token_resp

    def get(self, url, params=None, headers=None, **kw):
        self.calls.append(("GET", url, params))
        return self.get_responses.pop(0)


def _client(http):
    return HelloAssoClient("id", "secret", "bda-ens", http=http)


def test_asso_share_excludes_contribution():
    payment = {
        "amount": 1500,
        "state": "Authorized",
        "items": [
            {"amount": 1200, "type": "Membership"},
            {"amount": 300, "type": "Contribution"},
        ],
    }
    assert asso_share_cents(payment) == 1200


def test_asso_share_without_items_falls_back_to_amount():
    payment = {"amount": 1000, "state": "Authorized"}
    assert asso_share_cents(payment) == 1000


def test_get_token_calls_oauth_endpoint():
    http = FakeHttp(FakeResp(200, {"access_token": "tok", "expires_in": 1800}), [])
    c = _client(http)
    assert c._get_token() == "tok"
    assert http.calls[0][0] == "POST"
    assert "oauth2/token" in http.calls[0][1]


def test_get_token_error_raises():
    http = FakeHttp(FakeResp(401, {"error": "invalid_client"}), [])
    c = _client(http)
    with pytest.raises(HelloAssoError):
        c._get_token()


def test_get_token_malformed_body_raises():
    http = FakeHttp(FakeResp(200, {"expires_in": 1800}), [])
    c = _client(http)
    with pytest.raises(HelloAssoError):
        c._get_token()


def test_fetch_forms_paginates():
    token = FakeResp(200, {"access_token": "tok", "expires_in": 1800})
    page1 = FakeResp(200, {"data": [{"formType": "Membership", "formSlug": "cotis", "title": "Cotis", "state": "Public"}],
                           "pagination": {"continuationToken": "next"}})
    page2 = FakeResp(200, {"data": [{"formType": "Event", "formSlug": "gala", "title": "Gala", "state": "Public"}],
                           "pagination": {}})
    http = FakeHttp(token, [page1, page2])
    c = _client(http)
    forms = c.fetch_forms()
    assert len(forms) == 2
    assert forms[1]["formSlug"] == "gala"


def test_fetch_campaign_totals_aggregates(monkeypatch):
    c = _client(FakeHttp(FakeResp(200, {"access_token": "t", "expires_in": 1800}), []))
    monkeypatch.setattr(c, "fetch_forms", lambda: [
        {"formType": "Membership", "formSlug": "cotis", "title": "Cotisations", "state": "Public"},
    ])
    monkeypatch.setattr(c, "fetch_form_payments", lambda ft, fs, s, e: [
        {"amount": 1500, "state": "Authorized", "items": [{"amount": 1200, "type": "Membership"}, {"amount": 300, "type": "Contribution"}]},
        {"amount": 1200, "state": "Authorized", "items": [{"amount": 1200, "type": "Membership"}]},
        {"amount": 1200, "state": "Refused", "items": [{"amount": 1200, "type": "Membership"}]},
    ])
    totals = c.fetch_campaign_totals("2025-09-01", "2026-08-31")
    assert len(totals) == 1
    assert totals[0]["form_slug"] == "cotis"
    assert totals[0]["collected_cents"] == 2400  # 1200 + 1200, le Refused et la Contribution exclus
