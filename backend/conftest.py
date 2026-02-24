"""Pytest fixtures and configuration for backend tests."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _dev_auth_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure dev auth works in tests: set DEV_DEFAULT_USER_EMAIL so requests without X-Dev-User still authenticate."""
    monkeypatch.setattr("app.config.settings.dev_default_user_email", "test@example.com")
    monkeypatch.setattr("app.config.settings.environment", "dev")


def dev_admin_headers() -> dict[str, str]:
    """Headers for dev user with Admin role (for tests needing Admin/Planner)."""
    return {"X-Dev-User": json.dumps({"email": "admin@test.com", "name": "Admin", "roles": ["Admin"]})}


@pytest.fixture
def client() -> TestClient:
    """TestClient for API tests."""
    return TestClient(app)


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Headers for dev user with Admin role (for tests needing Admin/Planner)."""
    return dev_admin_headers()
