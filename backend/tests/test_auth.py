"""Unit tests for auth: header parsing (easy auth and dev), get_current_user."""
from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock

import pytest

from app.security.auth import (
    Identity,
    parse_dev_headers,
    parse_easy_auth_headers,
    VALID_ROLES,
)


def test_parse_easy_auth_principal_b64() -> None:
    """X-MS-CLIENT-PRINCIPAL base64 JSON: extract userId (oid) and userDetails (email)."""
    payload = {
        "userId": "oid-123",
        "userDetails": "user@example.com",
    }
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    req = MagicMock()
    req.headers = {"X-MS-CLIENT-PRINCIPAL": b64}
    identity = parse_easy_auth_headers(req)
    assert identity is not None
    assert identity.entra_oid == "oid-123"
    assert identity.email == "user@example.com"
    assert identity.runtime_roles is None


def test_parse_easy_auth_principal_with_oid_alias() -> None:
    """Support oid and user_id as aliases for userId."""
    payload = {"oid": "oid-456", "preferred_username": "upn@tenant.com"}
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    req = MagicMock()
    req.headers = {"X-MS-CLIENT-PRINCIPAL": b64}
    identity = parse_easy_auth_headers(req)
    assert identity is not None
    assert identity.entra_oid == "oid-456"
    assert identity.email == "upn@tenant.com"


def test_parse_easy_auth_fallback_headers() -> None:
    """Fallback to X-MS-CLIENT-PRINCIPAL-NAME and X-MS-CLIENT-PRINCIPAL-ID."""
    req = MagicMock()
    req.headers = {
        "X-MS-CLIENT-PRINCIPAL-NAME": "user@contoso.com",
        "X-MS-CLIENT-PRINCIPAL-ID": "guid-789",
    }
    identity = parse_easy_auth_headers(req)
    assert identity is not None
    assert identity.entra_oid == "guid-789"
    assert identity.email == "user@contoso.com"


def test_parse_easy_auth_missing_returns_none() -> None:
    """No Easy Auth headers returns None."""
    req = MagicMock()
    req.headers = {}
    assert parse_easy_auth_headers(req) is None


def test_parse_dev_headers_json_with_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    """X-Dev-User JSON with roles: extract email, name, runtime_roles (dev only)."""
    monkeypatch.setattr("app.security.auth._is_dev_mode", lambda: True)
    req = MagicMock()
    req.headers = {
        "X-Dev-User": json.dumps({
            "email": "dev@local.com",
            "name": "Dev User",
            "roles": ["Admin", "Planner"],
        }),
    }
    identity = parse_dev_headers(req)
    assert identity is not None
    assert identity.email == "dev@local.com"
    assert identity.display_name == "Dev User"
    assert identity.runtime_roles == ["Admin", "Planner"]


def test_parse_dev_headers_plain_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """X-Dev-User as plain email string."""
    monkeypatch.setattr("app.security.auth._is_dev_mode", lambda: True)
    req = MagicMock()
    req.headers = {"X-Dev-User": "simple@test.com"}
    identity = parse_dev_headers(req)
    assert identity is not None
    assert identity.email == "simple@test.com"
    assert identity.runtime_roles is None


def test_parse_dev_headers_invalid_roles_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid role names in JSON are filtered out."""
    monkeypatch.setattr("app.security.auth._is_dev_mode", lambda: True)
    req = MagicMock()
    req.headers = {
        "X-Dev-User": json.dumps({
            "email": "x@y.com",
            "roles": ["Admin", "InvalidRole", "Viewer"],
        }),
    }
    identity = parse_dev_headers(req)
    assert identity is not None
    assert set(identity.runtime_roles or []) == {"Admin", "Viewer"}


def test_parse_dev_headers_not_in_dev_mode_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """When not in dev mode, parse_dev_headers returns None."""
    monkeypatch.setattr("app.security.auth._is_dev_mode", lambda: False)
    req = MagicMock()
    req.headers = {"X-Dev-User": "dev@test.com"}
    assert parse_dev_headers(req) is None


def test_parse_dev_headers_empty_uses_default_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """When X-Dev-User empty but DEV_DEFAULT_USER_EMAIL set, use it."""
    monkeypatch.setattr("app.security.auth._is_dev_mode", lambda: True)
    monkeypatch.setattr("app.config.settings.dev_default_user_email", "default@test.com")
    req = MagicMock()
    req.headers = {"X-Dev-User": ""}
    identity = parse_dev_headers(req)
    assert identity is not None
    assert identity.email == "default@test.com"
