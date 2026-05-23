"""Authentication for Plugfile — managed-provider JWT verification.

Plugfile delegates login to a managed auth provider (Supabase Auth, Auth0,
Clerk, …). The browser uses the provider's SDK to sign in with Google,
Facebook, Apple, or email and receives a signed **JWT**. The frontend sends
that token as ``Authorization: Bearer <jwt>`` on gated requests; this module
verifies it on the backend.

Verification is **provider-agnostic**: it validates the token's signature
against the provider's published **JWKS** (public keys — no shared secret on
the server) and checks issuer/audience/expiry. That works for any provider
that exposes a JWKS endpoint and asymmetric (RS256/ES256) tokens.

Configuration (environment variables — set these in production, never commit
secrets; the JWKS contains only public keys)::

    PLUGFILE_AUTH_JWKS_URL   the provider's JWKS endpoint, e.g.
                             https://<project>.supabase.co/auth/v1/.well-known/jwks.json
    PLUGFILE_AUTH_ISSUER     expected ``iss`` claim (optional but recommended)
    PLUGFILE_AUTH_AUDIENCE   expected ``aud`` claim (optional)
    PLUGFILE_AUTH_PROVIDER   display name shown to the frontend (e.g. "supabase")

**Open mode:** if ``PLUGFILE_AUTH_JWKS_URL`` is not set, authentication is
disabled and every request is treated as an anonymous user. The app then
behaves exactly as the pre-auth open web form (useful for local dev / demo).
This means gating is opt-in via configuration and never breaks an unconfigured
deployment.

FastAPI usage::

    from plugfile.auth import require_user, AuthUser

    @app.post("/api/secure")
    def secure(user: AuthUser = Depends(require_user)):
        return {"hello": user.email}
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException


# ---- config -----------------------------------------------------------------

def _env(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None


def auth_enabled() -> bool:
    """True when a JWKS URL is configured (i.e. login is enforced)."""
    return _env("PLUGFILE_AUTH_JWKS_URL") is not None


def public_config() -> dict[str, Any]:
    """Non-secret auth config the frontend may read to configure its SDK.

    Returns the provider label and any public client config supplied via env
    (e.g. Supabase URL + anon key — both are designed to be public). Never
    returns secrets/service keys.
    """
    return {
        "enabled": auth_enabled(),
        "provider": _env("PLUGFILE_AUTH_PROVIDER") or ("oidc" if auth_enabled() else None),
        # Public client config (safe to expose). Supabase anon key is public by
        # design; RLS protects the data.
        "supabase_url": _env("PLUGFILE_SUPABASE_URL"),
        "supabase_anon_key": _env("PLUGFILE_SUPABASE_ANON_KEY"),
    }


# ---- user model -------------------------------------------------------------

@dataclass(frozen=True)
class AuthUser:
    """An authenticated principal (or the anonymous user in open mode)."""
    sub: str                       # provider subject id ("anonymous" when open)
    email: Optional[str] = None
    name: Optional[str] = None
    provider: Optional[str] = None
    is_authenticated: bool = False
    claims: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub": self.sub,
            "email": self.email,
            "name": self.name,
            "provider": self.provider,
            "is_authenticated": self.is_authenticated,
        }


ANONYMOUS = AuthUser(sub="anonymous", is_authenticated=False)


# ---- JWKS client (cached) ---------------------------------------------------

_jwks_lock = threading.Lock()
_jwks_client: Any = None
_jwks_url_cached: str | None = None


def _get_jwks_client():
    """Return a cached PyJWKClient for the configured JWKS URL."""
    global _jwks_client, _jwks_url_cached
    url = _env("PLUGFILE_AUTH_JWKS_URL")
    if url is None:
        return None
    with _jwks_lock:
        if _jwks_client is None or _jwks_url_cached != url:
            try:
                from jwt import PyJWKClient
            except ImportError as exc:  # pragma: no cover
                raise HTTPException(
                    status_code=500,
                    detail="PyJWT not installed — `pip install .[web]` to enable auth.",
                ) from exc
            _jwks_client = PyJWKClient(url, cache_keys=True)
            _jwks_url_cached = url
        return _jwks_client


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def verify_token(token: str) -> AuthUser:
    """Verify a provider JWT and return the :class:`AuthUser`.

    Raises HTTPException(401) on any verification failure.
    """
    import jwt  # PyJWT

    client = _get_jwks_client()
    if client is None:
        # Shouldn't happen (callers check auth_enabled first), but be safe.
        raise HTTPException(status_code=500, detail="Auth not configured.")

    issuer = _env("PLUGFILE_AUTH_ISSUER")
    audience = _env("PLUGFILE_AUTH_AUDIENCE")
    try:
        signing_key = client.get_signing_key_from_jwt(token).key
        options = {"verify_aud": audience is not None}
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256", "RS512", "ES384"],
            audience=audience,
            issuer=issuer,
            options=options,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    return AuthUser(
        sub=str(claims.get("sub", "")),
        email=claims.get("email"),
        name=claims.get("name") or claims.get("full_name"),
        provider=_env("PLUGFILE_AUTH_PROVIDER") or "oidc",
        is_authenticated=True,
        claims=claims,
    )


# ---- FastAPI dependencies ---------------------------------------------------

def optional_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """Return the authenticated user, or ANONYMOUS.

    In open mode (no JWKS configured) always returns ANONYMOUS. When auth is
    enabled, a present-but-invalid token still raises 401; a missing token
    returns ANONYMOUS (caller decides whether that's allowed).
    """
    if not auth_enabled():
        return ANONYMOUS
    token = _bearer_token(authorization)
    if token is None:
        return ANONYMOUS
    return verify_token(token)


def require_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """Require an authenticated user on gated endpoints.

    Open mode (no provider configured): returns ANONYMOUS so the app keeps
    working as an open web form. When auth is enabled: a valid Bearer token is
    required, else 401.
    """
    if not auth_enabled():
        return ANONYMOUS
    token = _bearer_token(authorization)
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Sign in to use this feature.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token(token)
