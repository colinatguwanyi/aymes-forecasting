"""
Postgres SOH adapter: reads current weekly stock-on-hand from the existing
inventory_snapshots_weekly table and returns it as forecast_stock_weekly rows.

This is an adapter layer — it reads from the platform's canonical SOH store
and produces dicts suitable for upserting into forecast_stock_weekly.
It never writes directly to inventory_snapshots_weekly.

SOH mapping assumption:
    inventory_snapshots_weekly.(sku, warehouse_code, week_start, on_hand_qty)
    → forecast_stock_weekly.(sku, warehouse_code, week_start, on_hand_qty)
    source = 'inventory_snapshots_weekly'

When multiple source_type rows exist for the same (sku, warehouse, week),
'soh' is preferred over 'legacy' (mirrors the stock coverage report logic).
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import InventorySnapshotWeekly

logger = logging.getLogger(__name__)

_SOURCE_LABEL = "inventory_snapshots_weekly"


class PostgresSOHAdapter:
    """
    Reads SOH data from inventory_snapshots_weekly for use by the forecasting engine.

    Usage:
        adapter = PostgresSOHAdapter(db)
        rows = adapter.read_latest_soh(warehouse_codes=["AAH", "BLP"])
        # Each dict: sku, warehouse_code, week_start, on_hand_qty, source

    The rows returned are suitable for upserting into forecast_stock_weekly.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def read_latest_soh(
        self,
        warehouse_codes: list[str] | None = None,
        as_of_week: date | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return the latest SOH per (sku, warehouse_code) from inventory_snapshots_weekly.

        If as_of_week is provided, only snapshots with week_start <= as_of_week
        are considered (useful for reproducible historical runs).

        If warehouse_codes is None, all warehouses are included.

        Returns a list of dicts:
            sku, warehouse_code, week_start (date), on_hand_qty (Decimal),
            source (str)
        """
        q = self._db.query(InventorySnapshotWeekly)
        if as_of_week is not None:
            q = q.filter(InventorySnapshotWeekly.week_start <= as_of_week)
        if warehouse_codes:
            upper_codes = [c.strip().upper() for c in warehouse_codes]
            q = q.filter(
                func.upper(InventorySnapshotWeekly.warehouse_code).in_(upper_codes)
            )

        all_rows = q.all()
        if not all_rows:
            logger.info("PostgresSOHAdapter: no inventory_snapshots_weekly rows found")
            return []

        # Deduplicate: per (sku, warehouse_code) keep the row with the latest
        # week_start; if tie on week_start prefer source_type='soh' over 'legacy'.
        seen: dict[tuple[str, str], InventorySnapshotWeekly] = {}
        for row in all_rows:
            key = (str(row.sku), str(row.warehouse_code).upper())
            existing = seen.get(key)
            if existing is None:
                seen[key] = row
                continue
            existing_week: date = existing.week_start  # type: ignore[assignment]
            row_week: date = row.week_start  # type: ignore[assignment]
            if row_week > existing_week:
                seen[key] = row
            elif row_week == existing_week and str(row.source_type) == "soh" and str(existing.source_type) != "soh":
                seen[key] = row

        result: list[dict[str, Any]] = []
        for row in seen.values():
            on_hand = (
                Decimal(str(row.on_hand_qty))
                if row.on_hand_qty is not None
                else Decimal("0")
            )
            result.append(
                {
                    "sku": str(row.sku),
                    "warehouse_code": str(row.warehouse_code).upper(),
                    "week_start": row.week_start,
                    "on_hand_qty": on_hand,
                    "source": _SOURCE_LABEL,
                }
            )

        logger.info(
            "PostgresSOHAdapter: returned %d deduplicated SOH rows (from %d raw rows)",
            len(result),
            len(all_rows),
        )
        return result

    def read_history(
        self,
        sku: str,
        warehouse_code: str,
        from_week: date,
        to_week: date,
    ) -> list[dict[str, Any]]:
        """
        Return all weekly SOH rows for a specific (sku, warehouse_code) in a
        date range.  Useful for building stock-state time series.
        """
        rows = (
            self._db.query(InventorySnapshotWeekly)
            .filter(
                InventorySnapshotWeekly.sku == sku,
                func.upper(InventorySnapshotWeekly.warehouse_code)
                == warehouse_code.strip().upper(),
                InventorySnapshotWeekly.week_start >= from_week,
                InventorySnapshotWeekly.week_start <= to_week,
            )
            .order_by(InventorySnapshotWeekly.week_start)
            .all()
        )
        return [
            {
                "sku": str(r.sku),
                "warehouse_code": str(r.warehouse_code).upper(),
                "week_start": r.week_start,
                "on_hand_qty": (
                    Decimal(str(r.on_hand_qty))
                    if r.on_hand_qty is not None
                    else Decimal("0")
                ),
                "source_type": str(r.source_type),
                "source": _SOURCE_LABEL,
            }
            for r in rows
        ]
