"""Tests: admin data management summary, preview, reset gating (no destructive run in unit tests)."""
# pyright: reportMissingImports=false
from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from sqlalchemy.exc import OperationalError

from app.services.data_management import (
    RESET_CONFIRM_PHRASE,
    SCOPE_CONFIRM_PHRASES,
    _is_mysql_lock_wait_timeout,
    execute_reset,
    reset_allowed,
    reset_preview,
    summary,
)


@pytest.fixture
def db_session():
    from app.database import engine

    Session = sessionmaker(bind=engine, autoflush=True)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def test_reset_confirm_phrase_constant() -> None:
    assert RESET_CONFIRM_PHRASE == "RESET TEST DATA"
    assert SCOPE_CONFIRM_PHRASES["planning_runs_only"] == "RESET PLANNING RUNS"


def test_execute_reset_blocked_when_gate_closed(monkeypatch: pytest.MonkeyPatch, db_session) -> None:
    monkeypatch.setattr(
        "app.services.data_management.reset_allowed",
        lambda: (False, "blocked for test"),
    )
    r = execute_reset(db_session, "full_test_data", RESET_CONFIRM_PHRASE, "actor@test")
    assert r.ok is False
    assert "blocked" in r.message.lower()
    assert r.scope == "full_test_data"


def test_execute_reset_rejects_bad_confirm(monkeypatch: pytest.MonkeyPatch, db_session) -> None:
    monkeypatch.setattr(
        "app.services.data_management.reset_allowed",
        lambda: (True, ""),
    )
    r = execute_reset(db_session, "full_test_data", "wrong phrase", "actor@test")
    assert r.ok is False
    assert "Confirmation for scope" in r.message


def test_execute_reset_planning_scope_requires_matching_phrase(monkeypatch: pytest.MonkeyPatch, db_session) -> None:
    monkeypatch.setattr(
        "app.services.data_management.reset_allowed",
        lambda: (True, ""),
    )
    r = execute_reset(db_session, "planning_runs_only", RESET_CONFIRM_PHRASE, "actor@test")
    assert r.ok is False
    assert "RESET PLANNING RUNS" in r.message


def test_reset_preview_full_has_products(db_session) -> None:
    p = reset_preview(db_session, "full_test_data")
    assert p["scope"] == "full_test_data"
    assert "delete_order" in p
    assert "plan_runs" in p["delete_order"]
    assert "products" in p["delete_order"]
    assert p["confirm_phrase_required"] == RESET_CONFIRM_PHRASE


def test_reset_preview_planning_smaller(db_session) -> None:
    p = reset_preview(db_session, "planning_runs_only")
    assert p["scope"] == "planning_runs_only"
    assert "products" not in p["delete_order"]
    assert p["delete_order"][-1] == "plan_runs"


def test_reset_preview_invalid_scope(db_session) -> None:
    with pytest.raises(ValueError, match="Invalid reset scope"):
        reset_preview(db_session, "not_a_scope")


def test_summary_shape(db_session) -> None:
    s = summary(db_session)
    for key in (
        "environment",
        "reset_allowed",
        "product_count",
        "warehouse_count",
        "plan_run_count",
        "demand_row_count",
        "soh_weekly_row_count",
        "planning_policy_count",
        "suspicious_product_count",
        "suspicious_warehouse_count",
        "sku_integrity_highlights",
        "available_scopes",
    ):
        assert key in s
    assert isinstance(s["available_scopes"], list)
    assert any(x["id"] == "full_test_data" for x in s["available_scopes"])


def test_reset_allowed_default_dev() -> None:
    allowed, reason = reset_allowed()
    assert isinstance(allowed, bool)
    assert isinstance(reason, str)


def test_is_mysql_lock_wait_timeout_detects_1205() -> None:
    import pymysql.err

    exc = OperationalError("stmt", None, pymysql.err.OperationalError(1205, "Lock wait timeout exceeded"))
    assert _is_mysql_lock_wait_timeout(exc) is True
    exc2 = OperationalError("stmt", None, pymysql.err.OperationalError(1213, "Deadlock"))
    assert _is_mysql_lock_wait_timeout(exc2) is False


def test_execute_reset_lock_timeout_friendly_message(monkeypatch: pytest.MonkeyPatch, db_session) -> None:
    import pymysql.err

    monkeypatch.setattr(
        "app.services.data_management.reset_allowed",
        lambda: (True, ""),
    )

    real_execute = db_session.execute

    def delete_only_locks(stmt, *a, **kw):
        if "DELETE" in str(stmt).upper():
            raise OperationalError("x", None, pymysql.err.OperationalError(1205, "Lock wait timeout exceeded"))
        return real_execute(stmt, *a, **kw)

    monkeypatch.setattr(db_session, "execute", delete_only_locks)
    r = execute_reset(db_session, "policies", "RESET POLICIES", "actor@test")
    assert r.ok is False
    assert r.lock_timeout is True
    assert "locked" in r.message.lower()
    assert r.deleted_tables_committed == []
