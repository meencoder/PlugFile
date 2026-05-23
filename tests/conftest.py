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
