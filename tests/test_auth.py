"""Tests for managed-provider JWT auth (auth.py).

Uses a locally-generated RSA keypair (the JWKS client is monkeypatched to
return the public key) so the full verify path is exercised without a live
provider.
"""

from __future__ import annotations

import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from fastapi import HTTPException

import plugfile.auth as auth
from plugfile.auth import (
    ANONYMOUS,
    AuthUser,
    auth_enabled,
    optional_user,
    public_config,
    require_user,
    verify_token,
)


# ── keypair + JWKS stub ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


class _FakeKey:
    def __init__(self, key):
        self.key = key


class _FakeClient:
    def __init__(self, pub):
        self._pub = pub

    def get_signing_key_from_jwt(self, token):
        return _FakeKey(self._pub)


def _make_token(priv, **claims):
    payload = {
        "sub": "user-123",
        "email": "op@example.com",
        "name": "Op Example",
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
        **claims,
    }
    return jwt.encode(payload, priv, algorithm="RS256")


@pytest.fixture
def enabled(monkeypatch, keypair):
    """Auth enabled, JWKS client stubbed to the test public key."""
    priv, pub = keypair
    monkeypatch.setenv("PLUGFILE_AUTH_JWKS_URL", "https://example/jwks")
    monkeypatch.setenv("PLUGFILE_AUTH_PROVIDER", "supabase")
    monkeypatch.delenv("PLUGFILE_AUTH_ISSUER", raising=False)
    monkeypatch.delenv("PLUGFILE_AUTH_AUDIENCE", raising=False)
    monkeypatch.setattr(auth, "_get_jwks_client", lambda: _FakeClient(pub))
    return priv


# ── open mode (no provider configured) ──────────────────────────────────────

def test_open_mode_not_enabled(monkeypatch):
    monkeypatch.delenv("PLUGFILE_AUTH_JWKS_URL", raising=False)
    assert not auth_enabled()


def test_open_mode_require_user_returns_anonymous(monkeypatch):
    monkeypatch.delenv("PLUGFILE_AUTH_JWKS_URL", raising=False)
    u = require_user(authorization=None)
    assert u is ANONYMOUS
    assert not u.is_authenticated


def test_open_mode_ignores_any_token(monkeypatch):
    monkeypatch.delenv("PLUGFILE_AUTH_JWKS_URL", raising=False)
    u = optional_user(authorization="Bearer whatever")
    assert not u.is_authenticated


def test_public_config_open(monkeypatch):
    monkeypatch.delenv("PLUGFILE_AUTH_JWKS_URL", raising=False)
    cfg = public_config()
    assert cfg["enabled"] is False
    assert cfg["provider"] is None


# ── enabled mode ─────────────────────────────────────────────────────────────

def test_enabled_flag(enabled):
    assert auth_enabled()
    assert public_config()["enabled"] is True
    assert public_config()["provider"] == "supabase"


def test_valid_token_authenticates(enabled):
    token = _make_token(enabled)
    u = require_user(authorization=f"Bearer {token}")
    assert isinstance(u, AuthUser)
    assert u.is_authenticated
    assert u.sub == "user-123"
    assert u.email == "op@example.com"
    assert u.provider == "supabase"


def test_missing_token_rejected_when_enabled(enabled):
    with pytest.raises(HTTPException) as ei:
        require_user(authorization=None)
    assert ei.value.status_code == 401


def test_optional_user_missing_token_is_anonymous(enabled):
    # optional_user tolerates a missing token even when enabled.
    u = optional_user(authorization=None)
    assert not u.is_authenticated


def test_garbage_token_rejected(enabled):
    with pytest.raises(HTTPException) as ei:
        require_user(authorization="Bearer not.a.jwt")
    assert ei.value.status_code == 401


def test_expired_token_rejected(enabled):
    token = _make_token(
        enabled, exp=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    )
    with pytest.raises(HTTPException) as ei:
        require_user(authorization=f"Bearer {token}")
    assert ei.value.status_code == 401


def test_issuer_mismatch_rejected(monkeypatch, enabled):
    monkeypatch.setenv("PLUGFILE_AUTH_ISSUER", "https://expected-issuer")
    token = _make_token(enabled, iss="https://wrong-issuer")
    with pytest.raises(HTTPException) as ei:
        verify_token(token)
    assert ei.value.status_code == 401


def test_issuer_match_accepted(monkeypatch, enabled):
    monkeypatch.setenv("PLUGFILE_AUTH_ISSUER", "https://expected-issuer")
    token = _make_token(enabled, iss="https://expected-issuer")
    u = verify_token(token)
    assert u.is_authenticated


def test_audience_enforced(monkeypatch, enabled):
    monkeypatch.setenv("PLUGFILE_AUTH_AUDIENCE", "plugfile-api")
    bad = _make_token(enabled, aud="someone-else")
    with pytest.raises(HTTPException):
        verify_token(bad)
    good = _make_token(enabled, aud="plugfile-api")
    assert verify_token(good).is_authenticated


# ── bearer parsing ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("header,expected", [
    ("Bearer abc.def.ghi", "abc.def.ghi"),
    ("bearer abc", "abc"),
    ("Basic xyz", None),
    ("", None),
    (None, None),
    ("Bearer", None),
])
def test_bearer_token_parsing(header, expected):
    assert auth._bearer_token(header) == expected
