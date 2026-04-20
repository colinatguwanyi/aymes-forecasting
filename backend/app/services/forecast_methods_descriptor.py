"""Forecast methods descriptor: single source of truth for governance/audit.

Stored as a static Python dict. Future-proof: can move to DB or file if needed.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

METHOD_VERSION = "2026.02.24"
UPDATED_AT = "2026-02-24T10:00:00Z"

FORECAST_METHODS_DOC: dict[str, object] = {
    "method_version": METHOD_VERSION,
    "updated_at": UPDATED_AT,
    "overview": {
        "description": "Weekly supply planning forecasting and demand resolution. Demand is produced from Sales Out (customer invoiced), Samples (withdrawals), Adjustments (manual), and Baseline forecasts. Planning integrates actuals, baseline, or blended demand with freeze windows and overrides.",
        "timezone": "Europe/London",
        "week_anchor": "W-TUE (Tuesday start)",
    },
    "inputs": {
        "sales_out": {
            "description": "Customer invoiced sales from ERP. Used for forecasting training set and operational actual demand.",
            "columns": ["AAH_Product_Code", "Invoiced_Qty", "Business_Processed_Date (DD/MM/YYYY)", "Branch", "Net_Sales_Value"],
            "grain": "invoice line",
            "maps_to": ["demand_actuals", "demand_facts_weekly"],
            "warehouse": "AAH",
            "demand_type": "CUSTOMER",
        },
        "samples": {
            "description": "Sample withdrawals. Treated as a separate demand type (SAMPLES). Included or excluded per planning policy (include_samples).",
            "columns": ["week_start", "sku", "warehouse_code", "demand_type=SAMPLES", "qty"],
            "grain": "week × sku × warehouse",
            "maps_to": ["demand_actuals", "demand_facts_weekly"],
            "demand_type": "SAMPLES",
        },
        "soh": {
            "description": "Stock On Hand snapshots. Used for starting stock and on-order in projections.",
            "columns": ["Stock at (date)", "Branch Name", "AAH Code", "STOCK", "ON ORDER"],
            "grain": "daily snapshot per branch × sku",
            "maps_to": ["inventory_snapshots_daily", "inventory_snapshots_weekly"],
            "branch_mapping": "warehouse_branch_mapping (Branch Name → warehouse_code)",
        },
        "baseline_forecasts": {
            "description": "Baseline forecast output from seasonal_naive_52 or external model. Published to published_baseline_forecasts_weekly.",
            "columns": ["aah_product_code", "forecast_week", "forecast", "model", "inference_date"],
            "grain": "week × sku × warehouse × train_end_week_start",
            "maps_to": ["baseline_forecasts_weekly", "published_baseline_forecasts_weekly"],
        },
    },
    "time_series_prep": {
        "calendar": "W-TUE (Tuesday–Monday weeks)",
        "bucket_rule": "week_start_for_date(d) returns the Tuesday that starts the week for any date d (London-local)",
        "dedupe_rules": [
            "Sales Out: aggregate by (week_start, sku) per run; AAH code → SKU via products.aah_code",
            "SOH: take latest as_of_date per (week_start, warehouse_code, sku) for weekly rollup",
            "Demand: unique (week_start, sku, warehouse_code, demand_type)",
        ],
        "unit_rules": [
            "Sales Out: Invoiced_Qty in selling units",
            "SOH: STOCK and ON ORDER in units",
            "Demand: qty in units",
        ],
        "cleaning": [
            "SKU mapping: sku_code_map (old_sku → new_sku) applied before aggregation",
            "MIN_WEEKS_HISTORY (60) enforced for demand_stage_weekly → demand_facts_weekly",
            "Missing weeks filled with qty=0, is_imputed=true",
        ],
    },
    "forecasting": {
        "modes": ["actuals", "baseline", "blended"],
        "actuals": "demand_actuals only (CUSTOMER + SAMPLES + ADJUSTMENT per policy)",
        "baseline": "published_baseline_forecasts_weekly; selected by train_end_week_start",
        "blended": "actuals for weeks <= run_week; baseline for weeks > run_week",
        "baseline_selection": "latest inference_date (or pinned selected_train_end_week_start)",
        "blending_rule": "actuals override inside freeze window; baseline outside; overrides always override",
        "exceptions": [
            "NoBaselineRunsError when demand_source=baseline and no published runs",
            "Unknown AAH code in Sales Out → rejected",
        ],
    },
    "planning_integration": {
        "demand_source": "actuals | baseline | blended (per plan_run)",
        "freeze_weeks": "First N weeks from plan_start_week_start (W-TUE): demand and orders inside frozen",
        "freeze_window_anchor": "plan_start_week_start = W-TUE week containing run_at",
        "overrides": "demand_overrides_weekly and planned_order_overrides_weekly; override reason_code and notes",
        "order_rounding": ["MOQ first (ceil to MOQ multiple); then pack_size (increment) if present"],
        "lead_time_sources": [
            "1. supplier_products.lead_time_weeks (lane) for primary supplier",
            "2. planning_policies: lead_time_production_weeks, lead_time_haulage_weeks, lead_time_putaway_weeks, lead_time_slot_wait_weeks, lead_time_padding_weeks",
            "3. effective_lead_time = max(supplier_lt, policy_production + haulage + putaway + slot + padding)",
        ],
    },
    "known_limitations": [
        "Missing SKUs: Sales Out rows with unknown AAH code are rejected",
        "Late postings: Sales Out processed_date may lag; no backfill of prior weeks",
        "Branch mapping gaps: SOH branches not in warehouse_branch_mapping are rejected",
        "Single warehouse: baseline/blended currently assumes AAH for forecast run selection",
        "Samples: include_samples per (sku, warehouse) via planning_policies; default true",
    ],
}


def _compute_hash(doc: dict[str, object]) -> str:
    """Stable SHA-256 hash of JSON-serialized doc (sorted keys for determinism)."""
    canonical = json.dumps(doc, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_forecast_methods_doc() -> dict[str, object]:
    """Return the full descriptor with audit hash."""
    doc = dict(FORECAST_METHODS_DOC)
    doc["audit"] = {"hash": _compute_hash(doc)}
    return doc


def get_method_version() -> str:
    return METHOD_VERSION


def get_updated_at() -> str:
    return UPDATED_AT
