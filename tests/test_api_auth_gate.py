"""API-level tests for auth gating of the paid PDF + the auth endpoints.

Verifies the open-mode (no provider configured) behaviour keeps the app fully
usable, and that enabling auth gates the paid/FINAL PDF while leaving the free
DRAFT tier and all prep endpoints open.
"""

from __future__ import annotations

import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

import plugfile.auth as auth
from plugfile.api import app

API = "42-371-30001"
GEN_BODY = {
    "api_number": API,
    "operator_signature_name": "Jane Operator",
    "operator_title": "VP Ops",
    "certification_date": "2026-05-23",
    "plugging_date": "2026-05-16",
}


@pytest.fixture
def client():
    return TestClient(app)


# ── open mode (default — no provider configured) ─────────────────────────────

def test_open_mode_config(client, monkeypatch):
    monkeypatch.delenv("PLUGFILE_AUTH_JWKS_URL", raising=False)
    r = client.get("/api/auth/config")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_open_mode_me_anonymous(client, monkeypatch):
    monkeypatch.delenv("PLUGFILE_AUTH_JWKS_URL", raising=False)
    r = client.get("/api/me")
    assert r.json()["is_authenticated"] is False


def test_open_mode_free_pdf_ok(client, monkeypatch):
    monkeypatch.delenv("PLUGFILE_AUTH_JWKS_URL", raising=False)
    r = client.post("/api/generate", json={**GEN_BODY, "paid_tier": False})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


def test_open_mode_paid_pdf_ok_without_login(client, monkeypatch):
    # Open mode: paid PDF works for everyone (app behaves as before auth).
    monkeypatch.delenv("PLUGFILE_AUTH_JWKS_URL", raising=False)
    r = client.post("/api/generate", json={**GEN_BODY, "paid_tier": True})
    assert r.status_code == 200


# ── enabled mode ─────────────────────────────────────────────────────────────

@pytest.fixture
def enabled(monkeypatch):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    monkeypatch.setenv("PLUGFILE_AUTH_JWKS_URL", "https://example/jwks")
    monkeypatch.setenv("PLUGFILE_AUTH_PROVIDER", "supabase")
    monkeypatch.delenv("PLUGFILE_AUTH_ISSUER", raising=False)
    monkeypatch.delenv("PLUGFILE_AUTH_AUDIENCE", raising=False)

    class _Key:
        def __init__(self, k): self.key = k

    class _Client:
        def get_signing_key_from_jwt(self, token): return _Key(pub)

    monkeypatch.setattr(auth, "_get_jwks_client", lambda: _Client())
    return priv


def _token(priv, **claims):
    payload = {
        "sub": "u1", "email": "op@example.com",
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
        **claims,
    }
    return jwt.encode(payload, priv, algorithm="RS256")


def test_enabled_config_exposes_provider(client, enabled):
    cfg = client.get("/api/auth/config").json()
    assert cfg["enabled"] is True
    assert cfg["provider"] == "supabase"


def test_enabled_free_pdf_still_open(client, enabled):
    # The free DRAFT tier must remain usable without logging in.
    r = client.post("/api/generate", json={**GEN_BODY, "paid_tier": False})
    assert r.status_code == 200


def test_enabled_paid_pdf_requires_login(client, enabled):
    r = client.post("/api/generate", json={**GEN_BODY, "paid_tier": True})
    assert r.status_code == 401


def test_enabled_paid_pdf_ok_with_token(client, enabled):
    tok = _token(enabled)
    r = client.post(
        "/api/generate", json={**GEN_BODY, "paid_tier": True},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


def test_enabled_me_with_token(client, enabled):
    tok = _token(enabled)
    r = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    body = r.json()
    assert body["is_authenticated"] is True
    assert body["email"] == "op@example.com"


def test_enabled_w3a_paid_requires_login(client, enabled):
    r = client.post("/api/w3a/generate", json={
        "api_number": API,
        "overrides": {"well_type": "oil", "completion_type": "single",
                      "operator_signature_name": "Jane", "operator_title": "VP",
                      "certification_date": "2026-05-23"},
        "paid_tier": True,
    })
    assert r.status_code == 401


def test_enabled_prep_endpoints_stay_open(client, enabled):
    # Non-paid prep endpoints (e.g. plug-program) are never gated.
    r = client.post("/api/plug-program", json={"api_number": API})
    assert r.status_code == 200
