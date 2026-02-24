"""Tests: sample_sales_soh_warehouses config — default BLP, multi-warehouse, exclude BLP, invalid fallback."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest  # type: ignore[reportMissingImports]

from app.services.app_settings import (
    DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES,
    get_sample_sales_soh_warehouses,
    get_setting_json,
    set_setting,
)


def _soh_schema_available() -> bool:
    from sqlalchemy import text
    try:
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            r = db.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'app_settings' LIMIT 1"
            ))
            return r.scalar() == 1
        finally:
            db.close()
    except Exception:
        return False


def test_get_setting_json_missing_returns_default() -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    result = get_setting_json(db, "sample_sales_soh_warehouses", ["BLP"])
    assert result == ["BLP"]


def test_get_sample_sales_soh_warehouses_default_when_not_set() -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    result = get_sample_sales_soh_warehouses(db)
    assert result == DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES


def test_get_sample_sales_soh_warehouses_invalid_not_list_fallback() -> None:
    db = MagicMock()
    row = MagicMock()
    row.value = "not-a-list"
    db.query.return_value.filter.return_value.first.return_value = row
    result = get_sample_sales_soh_warehouses(db)
    assert result == DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES


def test_get_sample_sales_soh_warehouses_invalid_non_string_elements_fallback() -> None:
    db = MagicMock()
    row = MagicMock()
    row.value = ["BLP", 123]
    db.query.return_value.filter.return_value.first.return_value = row
    result = get_sample_sales_soh_warehouses(db)
    assert result == DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 019 (app_settings) not applied")
def test_config_not_set_filters_to_blp_only() -> None:
    from app.database import SessionLocal
    from app.models import AppSettings

    db = SessionLocal()
    try:
        db.query(AppSettings).filter(AppSettings.key == "sample_sales_soh_warehouses").delete(synchronize_session=False)
        db.commit()
        result = get_sample_sales_soh_warehouses(db)
        assert result == ["BLP"]
    finally:
        set_setting(db, "sample_sales_soh_warehouses", ["BLP"])
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 019 (app_settings) not applied")
def test_config_blp_wh2_includes_both() -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        set_setting(db, "sample_sales_soh_warehouses", ["BLP", "WH2"])
        db.commit()
        result = get_sample_sales_soh_warehouses(db)
        assert result == ["BLP", "WH2"]
    finally:
        set_setting(db, "sample_sales_soh_warehouses", ["BLP"])
        db.commit()
        db.close()


@pytest.mark.skipif(not _soh_schema_available(), reason="Migration 019 (app_settings) not applied")
def test_config_wh2_only_excludes_blp() -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        set_setting(db, "sample_sales_soh_warehouses", ["WH2"])
        db.commit()
        result = get_sample_sales_soh_warehouses(db)
        assert result == ["WH2"]
        assert "BLP" not in result
    finally:
        set_setting(db, "sample_sales_soh_warehouses", ["BLP"])
        db.commit()
        db.close()
