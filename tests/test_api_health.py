"""Tests for the GET /api/health probe.

The endpoint is a lightweight liveness/version probe for deploy monitoring
(uptime checks, render.com health probes). It must stay open in every auth
mode and must reflect the active RRC fetcher selection.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from plugfile.api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_returns_ok_with_version(client, monkeypatch):
    monkeypatch.delenv("PLUGFILE_RRC_LIVE", raising=False)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]
    assert body["fetcher"] == "mock"


def test_health_reflects_live_fetcher(client, monkeypatch):
    monkeypatch.setenv("PLUGFILE_RRC_LIVE", "true")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["fetcher"] == "live"


def test_health_open_when_auth_enabled(client, monkeypatch):
    # Even with auth configured, /api/health stays open (no 401).
    monkeypatch.setenv("PLUGFILE_AUTH_JWKS_URL", "https://example/jwks")
    monkeypatch.setenv("PLUGFILE_AUTH_PROVIDER", "supabase")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
