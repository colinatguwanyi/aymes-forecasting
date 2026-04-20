"""App settings: key-value config with get_setting_json helper."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSettings

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES = ["BLP"]


def get_setting_json(db: Session, key: str, default: Any) -> Any:
    """Get JSON value for key; return default if not found or invalid."""
    row = db.query(AppSettings).filter(AppSettings.key == key).first()
    if not row or row.value is None:
        return default
    return row.value


def get_sample_sales_soh_warehouses(db: Session) -> list[str]:
    """
    Get warehouse codes for sample sales SOH filter. Default ["BLP"].
    If config value is invalid (not a list of strings), log warning and fallback to ["BLP"].
    """
    raw = get_setting_json(db, "sample_sales_soh_warehouses", DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES)
    if not isinstance(raw, list):
        logger.warning(
            "sample_sales_soh_warehouses config invalid (expected list of strings): %s",
            type(raw).__name__,
        )
        return DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES
    if not all(isinstance(x, str) for x in raw):
        logger.warning(
            "sample_sales_soh_warehouses config invalid (expected list of strings): non-string elements"
        )
        return DEFAULT_SAMPLE_SALES_SOH_WAREHOUSES
    return [str(x).strip() for x in raw if str(x).strip()]


def set_setting(db: Session, key: str, value: Any) -> None:
    """Set JSON value for key (upsert)."""
    row = db.query(AppSettings).filter(AppSettings.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSettings(key=key, value=value))
