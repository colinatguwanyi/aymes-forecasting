"""Admin test-data reset: read-only summary/preview and scoped deletes (non-prod only).

Deletes run one table per committed transaction to reduce lock contention vs one long transaction.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    DemandActual,
    DemandFactsWeekly,
    InventorySnapshotWeekly,
    PlanRun,
    PlanningPolicy,
    Product,
    Warehouse,
)

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_USER_MESSAGE = (
    "Reset could not run because database tables are locked. "
    "Close active app pages, restart backend/MySQL, then retry."
)

LOCK_TIMEOUT_RETRY_DELAY_SEC = 2.0

# Reset allowed only in these environment values (lowercased).
ALLOWED_RESET_ENVIRONMENTS = frozenset({"dev", "local", "development", "test"})

# Blocked production-like names (lowercased).
BLOCKED_RESET_ENVIRONMENTS = frozenset({"prod", "production", "staging", "uat", "live"})

# --- Full platform wipe (original behaviour) ---------------------------------
FULL_TEST_DATA_DELETE_TABLES: tuple[str, ...] = (
    "planned_orders",
    "projected_inventory",
    "plan_run_demand_inputs_weekly",
    "demand_overrides_weekly",
    "planned_order_overrides_weekly",
    "plan_run_freeze_events",
    "plan_run_events",
    "plan_runs",
    "demand_actuals",
    "demand_facts_weekly",
    "inventory_snapshots_daily",
    "inventory_snapshots_weekly",
    "receipts",
    "planning_policies",
    "published_baseline_forecasts_weekly",
    "baseline_forecasts_weekly",
    "forecast_run_metrics",
    "projections_weekly",
    "demand_weekly",
    "inbound_orders_weekly",
    "stock_positions_weekly",
    "warehouse_product_codes",
    "warehouse_branch_mapping",
    "warehouse_products",
    "supplier_products",
    "product_master_attributes",
    "lanes",
    "products",
    "warehouses",
    "demand_stage_weekly",
    "sales_out_stage",
    "stock_on_hand_stage",
    "forecast_run_output_stage",
    "product_master_stage",
    "ingestion_rejections",
    "ingestion_runs",
)

PLANNING_RUNS_ONLY_TABLES: tuple[str, ...] = (
    "planned_orders",
    "projected_inventory",
    "plan_run_demand_inputs_weekly",
    "demand_overrides_weekly",
    "planned_order_overrides_weekly",
    "plan_run_freeze_events",
    "plan_run_events",
    "plan_runs",
)

DEMAND_AND_SALES_TABLES: tuple[str, ...] = (
    "demand_actuals",
    "demand_facts_weekly",
    "demand_stage_weekly",
    "sales_out_stage",
)

SOH_INVENTORY_TABLES: tuple[str, ...] = (
    "inventory_snapshots_daily",
    "inventory_snapshots_weekly",
    "stock_on_hand_stage",
)

POLICIES_TABLES: tuple[str, ...] = ("planning_policies",)

# Product master + dependent SKU-keyed data (does not delete warehouses or ingestion runs).
PRODUCT_MASTER_TABLES: tuple[str, ...] = (
    "planned_orders",
    "projected_inventory",
    "plan_run_demand_inputs_weekly",
    "demand_overrides_weekly",
    "planned_order_overrides_weekly",
    "plan_run_freeze_events",
    "plan_run_events",
    "plan_runs",
    "demand_actuals",
    "demand_facts_weekly",
    "inventory_snapshots_daily",
    "inventory_snapshots_weekly",
    "receipts",
    "planning_policies",
    "published_baseline_forecasts_weekly",
    "baseline_forecasts_weekly",
    "forecast_run_metrics",
    "projections_weekly",
    "demand_weekly",
    "inbound_orders_weekly",
    "stock_positions_weekly",
    "warehouse_product_codes",
    "warehouse_products",
    "supplier_products",
    "product_master_attributes",
    "products",
)

# Warehouse master + warehouse-keyed facts and plan outputs (does not delete products/suppliers).
WAREHOUSE_MASTER_TABLES: tuple[str, ...] = (
    "planned_orders",
    "projected_inventory",
    "plan_run_demand_inputs_weekly",
    "demand_overrides_weekly",
    "planned_order_overrides_weekly",
    "plan_run_freeze_events",
    "plan_run_events",
    "plan_runs",
    "demand_actuals",
    "demand_facts_weekly",
    "inventory_snapshots_daily",
    "inventory_snapshots_weekly",
    "receipts",
    "planning_policies",
    "published_baseline_forecasts_weekly",
    "baseline_forecasts_weekly",
    "forecast_run_metrics",
    "projections_weekly",
    "demand_weekly",
    "inbound_orders_weekly",
    "stock_positions_weekly",
    "warehouse_product_codes",
    "warehouse_branch_mapping",
    "warehouse_products",
    "lanes",
    "warehouses",
)

MAPPINGS_TABLES: tuple[str, ...] = (
    "warehouse_product_codes",
    "warehouse_branch_mapping",
)

STAGING_AND_REJECTIONS_TABLES: tuple[str, ...] = (
    "demand_stage_weekly",
    "sales_out_stage",
    "stock_on_hand_stage",
    "forecast_run_output_stage",
    "product_master_stage",
    "ingestion_rejections",
    "ingestion_runs",
)

# Platform baseline + Admin Forecast Engine run data (not config/profile tables).
FORECAST_HISTORY_TABLES: tuple[str, ...] = (
    "published_baseline_forecasts_weekly",
    "baseline_forecasts_weekly",
    "forecast_run_metrics",
    "forecast_run_diagnostics",
    "forecast_results_weekly",
    "forecast_supply_adjusted",
    "forecast_training_series_weekly",
    "forecast_run_models",
    "forecast_runs",
    "forecast_sales_weekly",
    "forecast_stock_weekly",
)

SCOPE_DELETE_TABLES: dict[str, tuple[str, ...]] = {
    "full_test_data": FULL_TEST_DATA_DELETE_TABLES,
    "planning_runs_only": PLANNING_RUNS_ONLY_TABLES,
    "demand_and_sales": DEMAND_AND_SALES_TABLES,
    "soh_inventory": SOH_INVENTORY_TABLES,
    "policies": POLICIES_TABLES,
    "product_master": PRODUCT_MASTER_TABLES,
    "warehouse_master": WAREHOUSE_MASTER_TABLES,
    "mappings": MAPPINGS_TABLES,
    "staging_and_rejections": STAGING_AND_REJECTIONS_TABLES,
    "forecast_history": FORECAST_HISTORY_TABLES,
}

SCOPE_CONFIRM_PHRASES: dict[str, str] = {
    "full_test_data": "RESET TEST DATA",
    "planning_runs_only": "RESET PLANNING RUNS",
    "demand_and_sales": "RESET DEMAND",
    "soh_inventory": "RESET SOH",
    "policies": "RESET POLICIES",
    "product_master": "RESET PRODUCTS",
    "warehouse_master": "RESET WAREHOUSES",
    "mappings": "RESET MAPPINGS",
    "staging_and_rejections": "RESET STAGING",
    "forecast_history": "RESET FORECAST HISTORY",
}

SCOPE_DESCRIPTIONS: dict[str, str] = {
    "full_test_data": "All listed platform tables including products, warehouses, facts, plans, staging, and ingestion runs.",
    "planning_runs_only": "Plan run outputs and plan_run row graph only; preserves demand, SOH, policies, products.",
    "demand_and_sales": "Canonical demand and staged sales-out rows; does not clear ingestion_runs metadata.",
    "soh_inventory": "Inventory snapshots (daily/weekly) and SOH stage rows only.",
    "policies": "planning_policies only.",
    "product_master": "Deletes products after clearing all SKU-dependent facts, plans, mappings, and warehouse_product links (warehouses kept).",
    "warehouse_master": "Deletes warehouses after clearing warehouse-keyed facts, plans, mappings, lanes, and warehouse_products (products kept).",
    "mappings": "warehouse_product_codes and warehouse_branch_mapping only.",
    "staging_and_rejections": "Ingestion stage tables, rejections, and ingestion_runs.",
    "forecast_history": "Published/baseline platform forecasts, metrics, and forecast engine run/results/diagnostics/training/sales/stock tables; preserves config and product profiles.",
}

RESET_SCOPES: frozenset[str] = frozenset(SCOPE_DELETE_TABLES.keys())

# Backwards compatibility
RESET_CONFIRM_PHRASE = SCOPE_CONFIRM_PHRASES["full_test_data"]

# Reference list for UI: identity, app config, SKU remap, suppliers, calendar, and forecast *config* rows.
# (forecast_history deletes run/results/sales/stock engine tables but not these.)
PRESERVED_TABLES: tuple[str, ...] = (
    "users",
    "user_roles",
    "roles",
    "app_settings",
    "sku_code_map",
    "suppliers",
    "calendar_weeks",
    "forecast_source_configs",
    "forecast_runtime_configs",
    "forecast_product_profiles",
    "forecast_sku_history_rules",
)


def environment_label() -> str:
    return (settings.environment or "dev").strip() or "dev"


def reset_allowed() -> tuple[bool, str]:
    """Return (allowed, reason_if_not)."""
    env = environment_label().lower()
    if env in BLOCKED_RESET_ENVIRONMENTS:
        return False, f"Reset is blocked when ENVIRONMENT is '{environment_label()}' (production-like)."
    if env not in ALLOWED_RESET_ENVIRONMENTS:
        return (
            False,
            f"Reset is allowed only when ENVIRONMENT is one of {sorted(ALLOWED_RESET_ENVIRONMENTS)}; "
            f"current value is '{environment_label()}'.",
        )
    return True, ""


def normalize_scope(scope: str | None) -> str:
    s = (scope or "full_test_data").strip()
    if s not in SCOPE_DELETE_TABLES:
        raise ValueError(f"Invalid reset scope {s!r}. Allowed: {sorted(SCOPE_DELETE_TABLES)}")
    return s


def confirm_phrase_for_scope(scope: str) -> str:
    return SCOPE_CONFIRM_PHRASES[normalize_scope(scope)]


def available_scopes() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for sid in sorted(SCOPE_DELETE_TABLES.keys()):
        out.append(
            {
                "id": sid,
                "description": SCOPE_DESCRIPTIONS.get(sid, ""),
                "confirm_phrase_required": SCOPE_CONFIRM_PHRASES[sid],
            }
        )
    return out


def _existing_tables(bind: Any) -> set[str]:
    try:
        return set(inspect(bind).get_table_names())
    except Exception as exc:  # pragma: no cover
        logger.warning("data_management: could not introspect tables: %s", exc)
        return set()


def count_table(db: Session, table: str, existing: set[str]) -> int | None:
    if table not in existing:
        return None
    r = db.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar()
    return int(r) if r is not None else 0


def suspicious_product_count(db: Session) -> int:
    q = (
        db.query(func.count(Product.id))
        .filter(
            (Product.sku.like("WSP-%"))
            | (Product.sku.like("DWS-%"))
            | (Product.sku.like("SKU-%"))
            | (Product.sku.like("BULK-SKU-%"))
            | Product.name.in_(("P1", "P2", "P3", "P4"))
        )
        .scalar()
    )
    return int(q or 0)


def suspicious_warehouse_count(db: Session) -> int:
    """Heuristic: test helper pattern WH + 6 hex, or TEST*/TMP* prefixes (MySQL REGEXP)."""
    try:
        r = db.execute(
            text(
                """
                SELECT COUNT(*) FROM warehouses
                WHERE code REGEXP '^WH[0-9A-Fa-f]{6}$'
                   OR UPPER(code) LIKE 'TEST%'
                   OR UPPER(code) LIKE 'TMP%'
                """
            )
        ).scalar()
        return int(r or 0)
    except Exception as exc:
        logger.debug("suspicious_warehouse_count unavailable: %s", exc)
        return 0


def sku_integrity_highlights(db: Session) -> dict[str, Any]:
    """Subset of sku-integrity metrics (no new endpoints; reuse ORM patterns)."""
    orphan_policy = (
        db.query(func.count(PlanningPolicy.id))
        .outerjoin(Product, Product.sku == PlanningPolicy.sku)
        .filter(Product.id.is_(None))
        .scalar()
        or 0
    )
    orphan_demand = (
        db.query(func.count(func.distinct(DemandActual.sku)))
        .filter(~DemandActual.sku.in_(db.query(Product.sku)))
        .scalar()
        or 0
    )
    orphan_soh = (
        db.query(func.count(func.distinct(InventorySnapshotWeekly.sku)))
        .filter(~InventorySnapshotWeekly.sku.in_(db.query(Product.sku)))
        .scalar()
        or 0
    )
    orphan_facts = None
    try:
        orphan_facts = (
            db.query(func.count(func.distinct(DemandFactsWeekly.sku)))
            .filter(~DemandFactsWeekly.sku.in_(db.query(Product.sku)))
            .scalar()
            or 0
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("demand_facts_weekly orphan count: %s", exc)
        orphan_facts = None

    return {
        "orphan_planning_policy_sku_count": int(orphan_policy),
        "orphan_demand_actual_sku_distinct_count": int(orphan_demand),
        "orphan_inventory_snapshot_sku_distinct_count": int(orphan_soh),
        "orphan_demand_facts_sku_distinct_count": orphan_facts,
        "full_report_hint": "GET /api/v1/reports/data-health/sku-integrity for samples and full checks",
    }


def demand_row_count(db: Session) -> int:
    """Total demand_actuals rows (all types/warehouses)."""
    r = db.query(func.count(DemandActual.id)).scalar()
    return int(r or 0)


def soh_row_count(db: Session) -> int:
    r = db.query(func.count(InventorySnapshotWeekly.id)).scalar()
    return int(r or 0)


def summary(db: Session) -> dict[str, Any]:
    allowed, deny_reason = reset_allowed()
    prod_n = db.query(func.count(Product.id)).scalar() or 0
    wh_n = db.query(func.count(Warehouse.id)).scalar() or 0
    plan_n = db.query(func.count(PlanRun.id)).scalar() or 0
    pol_n = db.query(func.count(PlanningPolicy.id)).scalar() or 0
    return {
        "environment": environment_label(),
        "reset_allowed": allowed,
        "reset_blocked_reason": deny_reason if not allowed else None,
        "product_count": int(prod_n),
        "warehouse_count": int(wh_n),
        "plan_run_count": int(plan_n),
        "demand_row_count": demand_row_count(db),
        "soh_weekly_row_count": soh_row_count(db),
        "planning_policy_count": int(pol_n),
        "suspicious_product_count": suspicious_product_count(db),
        "suspicious_warehouse_count": suspicious_warehouse_count(db),
        "sku_integrity_highlights": sku_integrity_highlights(db),
        "available_scopes": available_scopes(),
    }


def _scope_warnings(scope_id: str) -> list[str]:
    w: list[str] = []
    if scope_id == "full_test_data":
        w.append("Most destructive scope: removes products, warehouses, and all listed operational data.")
    if scope_id == "product_master":
        w.append(
            "Includes dependent deletes: plan outputs, demand/SOH/receipts facts, policies, baseline/metrics, "
            "backbone weekly rows, warehouse_product_codes, warehouse_products, supplier_products, attributes."
        )
    if scope_id == "warehouse_master":
        w.append(
            "Includes dependent deletes: plan outputs, facts, policies, baseline, backbone rows, mappings, lanes."
        )
    if scope_id == "demand_and_sales":
        w.append("Does not delete ingestion_runs; SOH and policies unchanged.")
    if scope_id == "forecast_history":
        w.append(
            "Clears forecast_runs/results/diagnostics/training and synced forecast_sales_weekly/forecast_stock_weekly; "
            "preserves forecast_source_configs, forecast_runtime_configs, forecast_product_profiles, forecast_sku_history_rules."
        )
    if scope_id == "mappings":
        w.append("SOH resolution may fail until mappings are reloaded.")
    return w


def reset_preview(db: Session, scope: str | None = None) -> dict[str, Any]:
    scope_id = normalize_scope(scope)
    delete_tables = SCOPE_DELETE_TABLES[scope_id]
    bind = db.get_bind()
    existing = _existing_tables(bind)
    allowed, deny_reason = reset_allowed()
    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    warnings: list[str] = _scope_warnings(scope_id)
    for t in delete_tables:
        if t not in existing:
            skipped.append(t)
            continue
        c = count_table(db, t, existing)
        rows.append({"table": t, "row_count_before": c})
    if skipped:
        warnings.append(
            f"{len(skipped)} table(s) not present in this database and will be skipped: {', '.join(skipped[:25])}"
            + ("…" if len(skipped) > 25 else "")
        )
    if scope_id != "forecast_history":
        warnings.append(
            "Forecast engine config tables are never deleted by non-forecast_history scopes; "
            "use scope forecast_history to clear run/results data only."
        )
    if not allowed:
        warnings.insert(0, f"Reset execution is disabled: {deny_reason}")
    preserved = [{"table": t, "present": t in existing} for t in PRESERVED_TABLES]
    return {
        "scope": scope_id,
        "scope_description": SCOPE_DESCRIPTIONS.get(scope_id, ""),
        "environment": environment_label(),
        "reset_allowed": allowed,
        "reset_blocked_reason": deny_reason if not allowed else None,
        "affected_tables": rows,
        "delete_order": list(delete_tables),
        "skipped_tables": skipped,
        "preserved_tables": preserved,
        "warnings": warnings,
        "confirm_phrase_required": SCOPE_CONFIRM_PHRASES[scope_id],
    }


@dataclass
class ResetResult:
    """Result of execute_reset. deleted_tables_committed is non-empty only after a partial failure."""

    ok: bool
    message: str
    scope: str
    before_counts: dict[str, int | None]
    after_counts: dict[str, int | None]
    skipped_tables: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    deleted_tables_committed: list[str] = field(default_factory=list)
    lock_timeout: bool = False


def _is_mysql_lock_wait_timeout(exc: BaseException) -> bool:
    """MySQL 8 / InnoDB lock wait exceeded (1205)."""
    if isinstance(exc, OperationalError):
        orig = getattr(exc, "orig", None)
        if orig is not None and getattr(orig, "args", None):
            try:
                if int(orig.args[0]) == 1205:
                    return True
            except (TypeError, ValueError, IndexError):
                pass
    text_exc = str(exc).lower()
    return "1205" in str(exc) or "lock wait timeout" in text_exc


def _key_counts(db: Session, existing: set[str]) -> dict[str, int | None]:
    keys = (
        "products",
        "warehouses",
        "plan_runs",
        "demand_actuals",
        "inventory_snapshots_weekly",
        "planning_policies",
        "ingestion_runs",
    )
    return {k: count_table(db, k, existing) for k in keys}


def execute_reset(
    db: Session,
    scope: str | None,
    confirm_text: str,
    actor_email: str | None,
) -> ResetResult:
    try:
        scope_id = normalize_scope(scope)
    except ValueError as e:
        return ResetResult(False, str(e), (scope or "").strip() or "invalid", {}, {}, [], [str(e)])
    required = SCOPE_CONFIRM_PHRASES[scope_id]
    allowed, deny_reason = reset_allowed()
    if not allowed:
        return ResetResult(False, deny_reason, scope_id, {}, {}, [], [deny_reason])
    if (confirm_text or "").strip() != required:
        return ResetResult(
            False,
            f"Confirmation for scope {scope_id!r} must be exactly: {required!r}",
            scope_id,
            {},
            {},
            [],
            [],
        )

    delete_tables = SCOPE_DELETE_TABLES[scope_id]
    bind = db.get_bind()
    existing = _existing_tables(bind)
    skipped = [t for t in delete_tables if t not in existing]
    warnings: list[str] = list(_scope_warnings(scope_id))
    if skipped:
        warnings.append(f"Skipped missing tables: {', '.join(skipped)}")

    before = _key_counts(db, existing)

    # Clear session state; avoid holding a read transaction open across many DELETEs.
    db.rollback()
    db.expire_all()

    deleted_committed: list[str] = []
    for t in delete_tables:
        if t not in existing:
            continue
        last_err: BaseException | None = None
        for attempt in range(2):
            try:
                db.execute(text(f"DELETE FROM `{t}`"))
                db.commit()
                deleted_committed.append(t)
                last_err = None
                break
            except Exception as exc:
                db.rollback()
                last_err = exc
                if _is_mysql_lock_wait_timeout(exc) and attempt == 0:
                    logger.warning(
                        "data_management lock wait table=%s scope=%s retry_after_s=%s",
                        t,
                        scope_id,
                        LOCK_TIMEOUT_RETRY_DELAY_SEC,
                    )
                    time.sleep(LOCK_TIMEOUT_RETRY_DELAY_SEC)
                    continue
                break
        if last_err is not None:
            exc = last_err
            existing_after = _existing_tables(bind)
            after = _key_counts(db, existing_after)
            warn_extra = warnings + [str(exc)]
            if _is_mysql_lock_wait_timeout(exc):
                detail = LOCK_TIMEOUT_USER_MESSAGE
                if deleted_committed:
                    detail = (
                        f"{LOCK_TIMEOUT_USER_MESSAGE} "
                        f"Failed on `{t}` after {len(deleted_committed)} table(s) in this scope were already cleared."
                    )
                logger.exception(
                    "data_management reset lock timeout scope=%s table=%s committed=%s",
                    scope_id,
                    t,
                    deleted_committed,
                )
                return ResetResult(
                    False,
                    detail,
                    scope_id,
                    before,
                    after,
                    skipped,
                    warn_extra,
                    deleted_committed,
                    True,
                )
            logger.exception(
                "data_management reset failed scope=%s table=%s committed=%s: %s",
                scope_id,
                t,
                deleted_committed,
                exc,
            )
            msg = (
                f"Reset stopped partway: {len(deleted_committed)} table delete(s) were already committed "
                f"before failure on `{t}`: {exc}. Run preview and fix the issue before retrying."
            )
            return ResetResult(
                False,
                msg,
                scope_id,
                before,
                after,
                skipped,
                warn_extra,
                deleted_committed,
                False,
            )

    existing_after = _existing_tables(bind)
    after = _key_counts(db, existing_after)

    log_payload = {
        "event": "scoped_test_data_reset",
        "scope": scope_id,
        "actor_email": actor_email,
        "environment": environment_label(),
        "before_counts": before,
        "after_counts": after,
        "skipped_tables": skipped,
        "tables_deleted_committed": len(deleted_committed),
        "confirmation": required,
    }
    logger.info("data_management %s", log_payload)

    return ResetResult(
        True,
        f"Reset completed for scope {scope_id!r}.",
        scope_id,
        before,
        after,
        skipped,
        warnings,
        deleted_committed,
        False,
    )
