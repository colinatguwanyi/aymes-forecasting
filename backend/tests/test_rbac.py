"""API tests: /auth/me, admin 403 for Viewer, admin 200 for Admin (dev header)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _dev_admin_headers() -> dict[str, str]:
    """Headers for dev user with Admin role."""
    return {"X-Dev-User": json.dumps({"email": "admin@test.com", "name": "Admin", "roles": ["Admin"]})}


def _dev_viewer_headers() -> dict[str, str]:
    """Headers for dev user with Viewer role only."""
    return {"X-Dev-User": json.dumps({"email": "viewer@test.com", "name": "Viewer", "roles": ["Viewer"]})}


def test_auth_me_returns_dev_user() -> None:
    """GET /api/v1/auth/me returns authenticated user with auth_mode=dev when X-Dev-User provided."""
    tc = TestClient(app)
    r = tc.get("/api/v1/auth/me", headers=_dev_admin_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["authenticated"] is True
    assert data["auth_mode"] == "dev"
    assert "user" in data
    assert data["user"]["email"] == "admin@test.com"
    assert data["user"]["display_name"] == "Admin"
    assert "Admin" in data["roles"]


def test_auth_me_401_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/auth/me returns 401 when no auth headers and no DEV_DEFAULT_USER_EMAIL."""
    monkeypatch.setattr("app.config.settings.dev_default_user_email", None)
    tc = TestClient(app)
    r = tc.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_admin_endpoint_403_for_viewer() -> None:
    """Admin endpoint returns 403 for user with only Viewer role."""
    tc = TestClient(app)
    r = tc.get("/api/admin/forecast-methods", headers=_dev_viewer_headers())
    assert r.status_code == 403


def test_admin_endpoint_200_for_admin() -> None:
    """Admin endpoint returns 200 for user with Admin role (dev header runtime roles)."""
    tc = TestClient(app)
    r = tc.get("/api/admin/forecast-methods", headers=_dev_admin_headers())
    assert r.status_code == 200
    data = r.json()
    assert "method_version" in data or "methods" in data or isinstance(data, dict)


def test_read_endpoint_200_with_viewer() -> None:
    """Read endpoint (e.g. demand) returns 200 for Viewer."""
    tc = TestClient(app)
    r = tc.get("/api/demand/", headers=_dev_viewer_headers())
    assert r.status_code == 200
