"""Shared test configuration.

Tests marked `@pytest.mark.db` need a real PostgreSQL. They are skipped unless
TEST_DATABASE_URL is set (CI sets it; locally: `docker compose up db` + backend/.env).
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("TEST_DATABASE_URL"):
        return
    skip_db = pytest.mark.skip(reason="TEST_DATABASE_URL not set")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)
