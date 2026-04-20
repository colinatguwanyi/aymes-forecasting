"""Tests for RBAC bootstrap: first-admin allowlist in non-dev."""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import Role, User, UserRole
from app.security.rbac_bootstrap import bootstrap_admin_if_allowed, parse_email_allowlist


def test_parse_email_allowlist() -> None:
    """Comma-separated emails: trimmed, lowercased, deduplicated."""
    assert parse_email_allowlist("a@x.com, B@Y.COM , c@z.com") == {"a@x.com", "b@y.com", "c@z.com"}
    assert parse_email_allowlist("") == frozenset()
    assert parse_email_allowlist(None) == frozenset()
    assert parse_email_allowlist("  only@one.com  ") == {"only@one.com"}


def test_prod_mode_bootstrap_admin_persisted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prod mode: user with email in allowlist gets Admin persisted."""
    monkeypatch.setattr("app.config.settings.environment", "prod")
    monkeypatch.setattr("app.config.settings.rbac_bootstrap_admin_emails", "bootstrap-admin@contoso.com")
    payload = {"userId": "oid-bootstrap-1", "userDetails": "bootstrap-admin@contoso.com"}
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    tc = TestClient(app)
    r = tc.get("/api/v1/auth/me", headers={"X-MS-CLIENT-PRINCIPAL": b64})
    assert r.status_code == 200
    data = r.json()
    assert "Admin" in data["roles"]
    assert data["auth_mode"] == "easy_auth"
    r2 = tc.get("/api/admin/forecast-methods", headers={"X-MS-CLIENT-PRINCIPAL": b64})
    assert r2.status_code == 200


def test_prod_mode_not_in_allowlist_no_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prod mode: user not in allowlist does not get roles."""
    monkeypatch.setattr("app.config.settings.environment", "prod")
    monkeypatch.setattr("app.config.settings.rbac_bootstrap_admin_emails", "other@contoso.com")
    payload = {"userId": "oid-no-bootstrap", "userDetails": "not-in-allowlist@contoso.com"}
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    tc = TestClient(app)
    r = tc.get("/api/v1/auth/me", headers={"X-MS-CLIENT-PRINCIPAL": b64})
    assert r.status_code == 200
    data = r.json()
    assert "Admin" not in data["roles"]
    assert data["roles"] == []
    r2 = tc.get("/api/admin/forecast-methods", headers={"X-MS-CLIENT-PRINCIPAL": b64})
    assert r2.status_code == 403


def test_dev_mode_bootstrap_does_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dev mode: bootstrap does not run; user in allowlist gets Viewer default, not Admin from bootstrap."""
    monkeypatch.setattr("app.config.settings.environment", "dev")
    monkeypatch.setattr("app.config.settings.dev_default_user_email", None)
    monkeypatch.setattr("app.config.settings.rbac_bootstrap_admin_emails", "dev-bootstrap@test.com")
    tc = TestClient(app)
    r = tc.get(
        "/api/v1/auth/me",
        headers={"X-Dev-User": json.dumps({"email": "dev-bootstrap@test.com", "name": "Dev"})},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["auth_mode"] == "dev"
    assert "Viewer" in data["roles"]
    assert "Admin" not in data["roles"]


def test_bootstrap_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bootstrap is idempotent: second login does not duplicate Admin role."""
    monkeypatch.setattr("app.config.settings.environment", "prod")
    monkeypatch.setattr("app.config.settings.rbac_bootstrap_admin_emails", "idempotent@contoso.com")
    payload = {"userId": "oid-idem", "userDetails": "idempotent@contoso.com"}
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    tc = TestClient(app)
    r1 = tc.get("/api/v1/auth/me", headers={"X-MS-CLIENT-PRINCIPAL": b64})
    assert r1.status_code == 200
    assert "Admin" in r1.json()["roles"]
    r2 = tc.get("/api/v1/auth/me", headers={"X-MS-CLIENT-PRINCIPAL": b64})
    assert r2.status_code == 200
    assert "Admin" in r2.json()["roles"]
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "idempotent@contoso.com").first()
        assert user is not None
        admin_count = (
            db.query(UserRole)
            .join(Role)
            .filter(UserRole.user_id == user.id, Role.name == "Admin")
            .count()
        )
        assert admin_count == 1
    finally:
        db.close()
