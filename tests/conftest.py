"""
Shared pytest fixtures and configuration for the Plugfile test suite.

Live-RRC tests are skipped by default to keep `pytest` fast and offline-safe.
Run them explicitly with:

    pytest --live tests/test_rrc_live.py

or just the full suite with live tests included:

    pytest --live
"""

from __future__ import annotations

import pytest


_AUTH_ENV_VARS = (
    "PLUGFILE_AUTH_JWKS_URL", "PLUGFILE_AUTH_PROVIDER", "PLUGFILE_AUTH_ISSUER",
    "PLUGFILE_AUTH_AUDIENCE", "PLUGFILE_SUPABASE_URL", "PLUGFILE_SUPABASE_ANON_KEY",
)


@pytest.fixture(autouse=True)
def _hermetic_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test in auth "open mode", regardless of any local `.env`.

    `plugfile.api` / `gau_parser` call `_load_dotenv()` at import, which would
    otherwise leak a developer's real Supabase config into the test process and
    make open-mode assertions flaky. Tests that want auth enabled opt in via
    their own `monkeypatch.setenv`.
    """
    for var in _AUTH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Enable tests that make real HTTP requests to rrc.texas.gov",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: marks tests that require live RRC API access (skipped by default)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--live"):
        return  # user opted in — run everything

    skip_live = pytest.mark.skip(reason="Live RRC tests skipped; use --live to enable")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)
