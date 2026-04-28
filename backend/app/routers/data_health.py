"""Data health and setup readiness reports."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, exists, func
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DemandActual,
    DemandFactsWeekly,
    DemandType,
    IngestionEntity,
    IngestionRun,
    IngestionStatus,
    InventorySnapshotWeekly,
    PlanningPolicy,
    Product,
    Receipt,
    Warehouse,
    WarehouseProductCode,
)
from app.security.auth import require_any_auth

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_any_auth)])

_SAMPLE = 25
_RECENT_WEEKS = 26


@router.get("")
def get_data_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return data health metrics for setup readiness and reports."""
    # Products
    product_count = db.query(Product).count()
    active_count = db.query(Product).filter(Product.active.is_(True)).count()

    # Demand (Sales Out path: demand_actuals CUSTOMER AAH)
    demand_latest = (
        db.query(func.max(DemandActual.week_start))
        .filter(
            DemandActual.demand_type == DemandType.CUSTOMER,
            DemandActual.warehouse_code == "AAH",
        )
        .scalar()
    )
    demand_weeks = (
        db.query(func.count(func.distinct(DemandActual.week_start)))
        .filter(
            DemandActual.demand_type == DemandType.CUSTOMER,
            DemandActual.warehouse_code == "AAH",
        )
        .scalar()
        or 0
    )
    demand_skus = (
        db.query(func.count(func.distinct(DemandActual.sku)))
        .filter(
            DemandActual.demand_type == DemandType.CUSTOMER,
            DemandActual.warehouse_code == "AAH",
        )
        .scalar()
        or 0
    )

    # SOH
    soh_latest = (
        db.query(func.max(InventorySnapshotWeekly.week_start))
        .filter(InventorySnapshotWeekly.warehouse_code == "AAH")
        .scalar()
    )
    soh_skus = (
        db.query(func.count(func.distinct(InventorySnapshotWeekly.sku)))
        .filter(InventorySnapshotWeekly.warehouse_code == "AAH")
        .scalar()
        or 0
    )

    # Receipts (inbound next 8 weeks)
    warehouses = [w.code for w in db.query(Warehouse).filter(Warehouse.active.is_(True)).all()]
    today = date.today()
    eight_weeks_later = today + timedelta(days=56)
    receipts_skus = (
        db.query(func.count(func.distinct(Receipt.sku)))
        .filter(
            Receipt.warehouse_code.in_(warehouses or ["AAH"]),
            Receipt.week_start >= today,
            Receipt.week_start <= eight_weeks_later,
        )
        .scalar()
        or 0
    )
    receipts_latest = (
        db.query(func.max(Receipt.week_start))
        .filter(Receipt.warehouse_code.in_(warehouses or ["AAH"]))
        .scalar()
    )

    # BLP mapping (from latest SOH run progress_meta or unmapped)
    blp_coverage_pct: float | None = None
    units_missing_pct: float | None = None
    latest_soh = (
        db.query(IngestionRun)
        .filter(
            IngestionRun.entity == IngestionEntity.STOCK_ON_HAND,
            IngestionRun.status == IngestionStatus.SUCCESS,
        )
        # MySQL has no NULLS LAST; put non-null finished_at first, then newest first.
        .order_by(IngestionRun.finished_at.is_(None).asc(), IngestionRun.finished_at.desc())
        .first()
    )
    pm = getattr(latest_soh, "progress_meta", None) if latest_soh else None
    if isinstance(pm, dict):
        blp_coverage_pct = pm.get("pct_coverage_codes")
        units_missing_pct = pm.get("pct_units_missing")
    # Warehouse product codes count (BLP mapping table)
    wpc_count = db.query(WarehouseProductCode).filter(WarehouseProductCode.active.is_(True)).count()

    # Ready to plan
    policy_count = db.query(PlanningPolicy).count()
    required_policies = active_count * max(1, len(warehouses))
    ready = (
        product_count > 0
        and demand_latest is not None
        and soh_latest is not None
        and policy_count > 0
    )
    # Demand-only gate: policies + demand only (SOH not required)
    ready_for_demand_only = (
        product_count > 0
        and demand_latest is not None
        and policy_count > 0
    )

    return {
        "products": {"count": product_count, "active": active_count},
        "demand": {
            "latest_week": demand_latest.isoformat() if demand_latest else None,
            "weeks_available": demand_weeks,
            "skus_with_demand": demand_skus,
        },
        "soh": {
            "latest_week": soh_latest.isoformat() if soh_latest else None,
            "skus_with_stock": soh_skus,
        },
        "mapping": {
            "blp_coverage_pct": blp_coverage_pct,
            "units_missing_pct": units_missing_pct,
            "warehouse_product_codes_count": wpc_count,
        },
        "receipts": {
            "latest_week": receipts_latest.isoformat() if receipts_latest else None,
            "skus_with_inbound_next_8_weeks": receipts_skus,
        },
        "planning_policies": {"count": policy_count, "required_approx": required_policies},
        "warehouses_count": len(warehouses),
        "ready_to_plan": ready,
        "ready_for_demand_only": ready_for_demand_only,
    }


@router.get("/sku-integrity")
def get_sku_integrity_report(
    db: Session = Depends(get_db),
    sample_limit: int = Query(_SAMPLE, ge=1, le=100, description="Max sample rows per check"),
    recent_weeks: int = Query(_RECENT_WEEKS, ge=4, le=104, description="Weeks of history for recent demand/SOH"),
) -> dict[str, Any]:
    """
    Read-only diagnostics: canonical SKU (products.sku) alignment and planning coverage.
    No writes.
    """
    sample_limit = min(sample_limit, 100)
    today = date.today()
    max_demand_week = db.query(func.max(DemandActual.week_start)).scalar()
    max_soh_week = db.query(func.max(InventorySnapshotWeekly.week_start)).scalar()
    demand_cutoff = (
        cast(date, max_demand_week) - timedelta(days=recent_weeks * 7)
        if max_demand_week
        else today - timedelta(days=recent_weeks * 7)
    )
    soh_cutoff = (
        cast(date, max_soh_week) - timedelta(days=recent_weeks * 7)
        if max_soh_week
        else today - timedelta(days=recent_weeks * 7)
    )

    # 1) planning_policies.sku not in products
    orphan_policy_count = (
        db.query(func.count(PlanningPolicy.id))
        .outerjoin(Product, Product.sku == PlanningPolicy.sku)
        .filter(Product.id.is_(None))
        .scalar()
        or 0
    )
    orphan_policy_sample = [
        {"sku": r[0], "warehouse_code": r[1]}
        for r in (
            db.query(PlanningPolicy.sku, PlanningPolicy.warehouse_code)
            .outerjoin(Product, Product.sku == PlanningPolicy.sku)
            .filter(Product.id.is_(None))
            .limit(sample_limit)
            .all()
        )
    ]

    # 2) inventory_snapshots_weekly: distinct sku not in products
    orphan_soh_sku_count = (
        db.query(func.count(func.distinct(InventorySnapshotWeekly.sku)))
        .filter(~InventorySnapshotWeekly.sku.in_(db.query(Product.sku)))
        .scalar()
        or 0
    )
    orphan_soh_sample = [
        {"sku": r[0], "warehouse_code": r[1], "latest_week_start": r[2].isoformat() if r[2] else None}
        for r in (
            db.query(
                InventorySnapshotWeekly.sku,
                InventorySnapshotWeekly.warehouse_code,
                func.max(InventorySnapshotWeekly.week_start).label("lw"),
            )
            .filter(~InventorySnapshotWeekly.sku.in_(db.query(Product.sku)))
            .group_by(InventorySnapshotWeekly.sku, InventorySnapshotWeekly.warehouse_code)
            .limit(sample_limit)
            .all()
        )
    ]

    # 3) demand_actuals.sku not in products
    orphan_da_sku_count = (
        db.query(func.count(func.distinct(DemandActual.sku)))
        .filter(~DemandActual.sku.in_(db.query(Product.sku)))
        .scalar()
        or 0
    )
    orphan_da_sample = [
        {"sku": r[0], "warehouse_code": r[1], "latest_week_start": r[2].isoformat() if r[2] else None}
        for r in (
            db.query(
                DemandActual.sku,
                DemandActual.warehouse_code,
                func.max(DemandActual.week_start).label("lw"),
            )
            .filter(~DemandActual.sku.in_(db.query(Product.sku)))
            .group_by(DemandActual.sku, DemandActual.warehouse_code)
            .limit(sample_limit)
            .all()
        )
    ]

    demand_facts_block: dict[str, Any] = {
        "orphan_sku_distinct_count": None,
        "orphan_sample": [],
        "error": None,
    }
    demand_coverage_block: dict[str, Any] = {
        "pairs_only_in_demand_actuals": None,
        "pairs_only_in_demand_facts_weekly": None,
        "pairs_in_both": None,
        "sample_only_in_actuals": [],
        "sample_only_in_facts": [],
    }

    try:
        orphan_df_count = (
            db.query(func.count(func.distinct(DemandFactsWeekly.sku)))
            .filter(~DemandFactsWeekly.sku.in_(db.query(Product.sku)))
            .scalar()
            or 0
        )
        demand_facts_block["orphan_sku_distinct_count"] = orphan_df_count
        demand_facts_block["orphan_sample"] = [
            {"sku": r[0], "warehouse_code": r[1], "latest_week_start": r[2].isoformat() if r[2] else None}
            for r in (
                db.query(
                    DemandFactsWeekly.sku,
                    DemandFactsWeekly.warehouse_code,
                    func.max(DemandFactsWeekly.week_start).label("lw"),
                )
                .filter(~DemandFactsWeekly.sku.in_(db.query(Product.sku)))
                .group_by(DemandFactsWeekly.sku, DemandFactsWeekly.warehouse_code)
                .limit(sample_limit)
                .all()
            )
        ]

        da_dist = (
            db.query(DemandActual.sku, DemandActual.warehouse_code).distinct().subquery("da_pairs")
        )
        df_dist = (
            db.query(DemandFactsWeekly.sku, DemandFactsWeekly.warehouse_code).distinct().subquery("df_pairs")
        )

        pairs_both = (
            db.query(func.count())
            .select_from(
                da_dist.join(
                    df_dist,
                    and_(
                        da_dist.c.sku == df_dist.c.sku,
                        da_dist.c.warehouse_code == df_dist.c.warehouse_code,
                    ),
                )
            )
            .scalar()
            or 0
        )
        pairs_only_da = (
            db.query(func.count())
            .select_from(
                da_dist.outerjoin(
                    df_dist,
                    and_(
                        da_dist.c.sku == df_dist.c.sku,
                        da_dist.c.warehouse_code == df_dist.c.warehouse_code,
                    ),
                )
            )
            .filter(df_dist.c.sku.is_(None))
            .scalar()
            or 0
        )
        pairs_only_df = (
            db.query(func.count())
            .select_from(
                df_dist.outerjoin(
                    da_dist,
                    and_(
                        df_dist.c.sku == da_dist.c.sku,
                        df_dist.c.warehouse_code == da_dist.c.warehouse_code,
                    ),
                )
            )
            .filter(da_dist.c.sku.is_(None))
            .scalar()
            or 0
        )
        demand_coverage_block["pairs_in_both"] = int(pairs_both)
        demand_coverage_block["pairs_only_in_demand_actuals"] = int(pairs_only_da)
        demand_coverage_block["pairs_only_in_demand_facts_weekly"] = int(pairs_only_df)

        only_da_q = (
            db.query(da_dist.c.sku, da_dist.c.warehouse_code)
            .select_from(
                da_dist.outerjoin(
                    df_dist,
                    and_(
                        da_dist.c.sku == df_dist.c.sku,
                        da_dist.c.warehouse_code == df_dist.c.warehouse_code,
                    ),
                )
            )
            .filter(df_dist.c.sku.is_(None))
            .limit(sample_limit)
        )
        demand_coverage_block["sample_only_in_actuals"] = [
            {"sku": r[0], "warehouse_code": r[1]} for r in only_da_q.all()
        ]
        only_df_q = (
            db.query(df_dist.c.sku, df_dist.c.warehouse_code)
            .select_from(
                df_dist.outerjoin(
                    da_dist,
                    and_(
                        df_dist.c.sku == da_dist.c.sku,
                        df_dist.c.warehouse_code == da_dist.c.warehouse_code,
                    ),
                )
            )
            .filter(da_dist.c.sku.is_(None))
            .limit(sample_limit)
        )
        demand_coverage_block["sample_only_in_facts"] = [
            {"sku": r[0], "warehouse_code": r[1]} for r in only_df_q.all()
        ]
    except ProgrammingError as e:
        logger.warning("sku-integrity: demand_facts_weekly unavailable: %s", e)
        demand_facts_block["error"] = "demand_facts_weekly query failed (table missing or DB error)."
        demand_coverage_block["error"] = demand_facts_block["error"]
        demand_coverage_block["pairs_in_both"] = None
        demand_coverage_block["pairs_only_in_demand_actuals"] = None
        demand_coverage_block["pairs_only_in_demand_facts_weekly"] = None
        demand_coverage_block["sample_only_in_actuals"] = []
        demand_coverage_block["sample_only_in_facts"] = []

    # 6) demand pair but no SOH pair (ever)
    soh_dist = (
        db.query(InventorySnapshotWeekly.sku, InventorySnapshotWeekly.warehouse_code)
        .distinct()
        .subquery("soh_pairs")
    )
    da_dist_all = db.query(DemandActual.sku, DemandActual.warehouse_code).distinct().subquery("da_all")
    demand_no_soh_count = (
        db.query(func.count())
        .select_from(
            da_dist_all.outerjoin(
                soh_dist,
                and_(
                    da_dist_all.c.sku == soh_dist.c.sku,
                    da_dist_all.c.warehouse_code == soh_dist.c.warehouse_code,
                ),
            )
        )
        .filter(soh_dist.c.sku.is_(None))
        .scalar()
        or 0
    )
    demand_no_soh_sample = [
        {"sku": r[0], "warehouse_code": r[1]}
        for r in (
            db.query(da_dist_all.c.sku, da_dist_all.c.warehouse_code)
            .select_from(
                da_dist_all.outerjoin(
                    soh_dist,
                    and_(
                        da_dist_all.c.sku == soh_dist.c.sku,
                        da_dist_all.c.warehouse_code == soh_dist.c.warehouse_code,
                    ),
                )
            )
            .filter(soh_dist.c.sku.is_(None))
            .limit(sample_limit)
            .all()
        )
    ]

    # 7) SOH pair but no planning policy
    pol_dist = (
        db.query(PlanningPolicy.sku, PlanningPolicy.warehouse_code).distinct().subquery("pol_pairs")
    )
    soh_no_policy_count = (
        db.query(func.count())
        .select_from(
            soh_dist.outerjoin(
                pol_dist,
                and_(
                    soh_dist.c.sku == pol_dist.c.sku,
                    soh_dist.c.warehouse_code == pol_dist.c.warehouse_code,
                ),
            )
        )
        .filter(pol_dist.c.sku.is_(None))
        .scalar()
        or 0
    )
    soh_no_policy_sample = [
        {"sku": r[0], "warehouse_code": r[1]}
        for r in (
            db.query(soh_dist.c.sku, soh_dist.c.warehouse_code)
            .select_from(
                soh_dist.outerjoin(
                    pol_dist,
                    and_(
                        soh_dist.c.sku == pol_dist.c.sku,
                        soh_dist.c.warehouse_code == pol_dist.c.warehouse_code,
                    ),
                )
            )
            .filter(pol_dist.c.sku.is_(None))
            .limit(sample_limit)
            .all()
        )
    ]

    # 8) policy but no recent demand
    has_recent_demand = exists().where(
        and_(
            DemandActual.sku == PlanningPolicy.sku,
            DemandActual.warehouse_code == PlanningPolicy.warehouse_code,
            DemandActual.week_start >= demand_cutoff,
        )
    )
    policy_no_recent_demand_count = (
        db.query(func.count(PlanningPolicy.id)).filter(~has_recent_demand).scalar() or 0
    )
    policy_no_recent_demand_sample = [
        {"sku": r[0], "warehouse_code": r[1]}
        for r in (
            db.query(PlanningPolicy.sku, PlanningPolicy.warehouse_code)
            .filter(~has_recent_demand)
            .limit(sample_limit)
            .all()
        )
    ]

    # 9) policy but no recent SOH
    has_recent_soh = exists().where(
        and_(
            InventorySnapshotWeekly.sku == PlanningPolicy.sku,
            InventorySnapshotWeekly.warehouse_code == PlanningPolicy.warehouse_code,
            InventorySnapshotWeekly.week_start >= soh_cutoff,
        )
    )
    policy_no_recent_soh_count = (
        db.query(func.count(PlanningPolicy.id)).filter(~has_recent_soh).scalar() or 0
    )
    policy_no_recent_soh_sample = [
        {"sku": r[0], "warehouse_code": r[1]}
        for r in (
            db.query(PlanningPolicy.sku, PlanningPolicy.warehouse_code)
            .filter(~has_recent_soh)
            .limit(sample_limit)
            .all()
        )
    ]

    # Plan coverage: policy SKU×warehouse pairs that have at least one demand_actuals row and one SOH snapshot row
    has_any_demand_pol = exists().where(
        and_(
            DemandActual.sku == PlanningPolicy.sku,
            DemandActual.warehouse_code == PlanningPolicy.warehouse_code,
        )
    )
    has_any_soh_pol = exists().where(
        and_(
            InventorySnapshotWeekly.sku == PlanningPolicy.sku,
            InventorySnapshotWeekly.warehouse_code == PlanningPolicy.warehouse_code,
        )
    )
    plan_coverage_numerator = (
        db.query(func.count(PlanningPolicy.id))
        .filter(has_any_demand_pol, has_any_soh_pol)
        .scalar()
        or 0
    )
    plan_coverage_denominator = db.query(func.count(PlanningPolicy.id)).scalar() or 0
    plan_coverage_ratio: float | None = (
        float(plan_coverage_numerator) / float(plan_coverage_denominator)
        if plan_coverage_denominator
        else None
    )
    demand_pair_total = db.query(func.count()).select_from(da_dist_all).scalar() or 0
    demand_without_soh_ratio = (
        float(demand_no_soh_count) / float(demand_pair_total) if demand_pair_total else 0.0
    )

    return {
        "generated_at": today.isoformat(),
        "parameters": {
            "sample_limit": sample_limit,
            "recent_weeks": recent_weeks,
            "recent_demand_cutoff_week_start": demand_cutoff.isoformat(),
            "recent_soh_cutoff_week_start": soh_cutoff.isoformat(),
            "anchor_demand_latest_week": max_demand_week.isoformat() if max_demand_week else None,
            "anchor_soh_latest_week": max_soh_week.isoformat() if max_soh_week else None,
        },
        "orphan_skus": {
            "planning_policy_rows": {"count": int(orphan_policy_count), "sample": orphan_policy_sample},
            "inventory_snapshots_weekly_distinct_sku": {
                "count": int(orphan_soh_sku_count),
                "sample": orphan_soh_sample,
            },
            "demand_actuals_distinct_sku": {"count": int(orphan_da_sku_count), "sample": orphan_da_sample},
            "demand_facts_weekly_distinct_sku": demand_facts_block,
        },
        "demand_actuals_vs_demand_facts_pairs": demand_coverage_block,
        "coverage_gaps": {
            "demand_pair_no_soh_pair_ever": {
                "pair_count": int(demand_no_soh_count),
                "sample": demand_no_soh_sample,
            },
            "soh_pair_no_planning_policy": {
                "pair_count": int(soh_no_policy_count),
                "sample": soh_no_policy_sample,
            },
            "planning_policy_no_recent_demand": {
                "pair_count": int(policy_no_recent_demand_count),
                "sample": policy_no_recent_demand_sample,
            },
            "planning_policy_no_recent_soh": {
                "pair_count": int(policy_no_recent_soh_count),
                "sample": policy_no_recent_soh_sample,
            },
        },
        "plan_coverage": {
            "numerator": int(plan_coverage_numerator),
            "denominator": int(plan_coverage_denominator),
            "ratio": plan_coverage_ratio,
        },
        "demand_without_soh_ratio": demand_without_soh_ratio,
    }
