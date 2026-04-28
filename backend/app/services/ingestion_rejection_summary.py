"""Aggregate ingestion rejections for cleanup workflows (e.g. missing SKUs after demand transform)."""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import DemandStageWeekly, IngestionRejection, IngestionRun

REASON_SKU_NOT_FOUND = "SKU not found or inactive"


def _payload_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


def build_rejection_summary(db: Session, run_id: UUID) -> dict[str, Any]:
    """
    Load all rejections for a run and return counts plus demand-specific rollups
    (missing / inactive SKUs, insufficient history).
    """
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        return {}

    rejs = (
        db.query(IngestionRejection)
        .filter(IngestionRejection.ingestion_run_id == run_id)
        .all()
    )

    reason_counts = Counter(r.reason for r in rejs)
    by_reason = [{"reason": reason, "count": count} for reason, count in reason_counts.most_common()]

    stages_by_id = {
        cast(int, s.id): s
        for s in db.query(DemandStageWeekly).filter(DemandStageWeekly.ingestion_run_id == run_id).all()
    }

    sku_nf: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    insuf: dict[tuple[str, str, str], dict[str, Any]] = {}

    for r in rejs:
        reason = cast(str, r.reason)
        payload = _payload_dict(r.raw_payload)
        if reason == REASON_SKU_NOT_FOUND:
            sku_raw = str(payload.get("sku_raw") or "").strip()
            mapped = str(payload.get("sku") or "").strip()
            wh = ""
            dt = ""
            st = stages_by_id.get(cast(int, r.row_number))
            if st is not None:
                wh = str(cast(str, st.warehouse_code) or "")
                dt_val = getattr(st, "demand_type", None)
                dt = dt_val.value if dt_val is not None else ""
            key = (sku_raw, mapped, wh, dt)
            if key not in sku_nf:
                sku_nf[key] = {
                    "sku_raw": sku_raw,
                    "sku_after_code_map": mapped or None,
                    "warehouse_code": wh or None,
                    "demand_type": dt or None,
                    "rejection_count": 0,
                    "sample_week_starts": [],
                }
            sku_nf[key]["rejection_count"] += 1
            wk = str(payload.get("week_start") or "").strip()
            samples: list[str] = sku_nf[key]["sample_week_starts"]
            if wk and wk not in samples and len(samples) < 5:
                samples.append(wk)
        elif reason.startswith("Insufficient history:"):
            sku = str(payload.get("sku") or "").strip()
            wh = str(payload.get("warehouse_code") or "").strip()
            dt = str(payload.get("demand_type") or "").strip()
            key2 = (sku, wh, dt)
            if key2 not in insuf:
                insuf[key2] = {
                    "sku": sku,
                    "warehouse_code": wh or None,
                    "demand_type": dt or None,
                    "rejection_count": 0,
                    "reason_detail": reason,
                }
            insuf[key2]["rejection_count"] += 1

    sku_nf_rows = sorted(
        sku_nf.values(),
        key=lambda x: (-int(x["rejection_count"]), str(x["sku_raw"])),
    )
    insuf_rows = sorted(
        insuf.values(),
        key=lambda x: (-int(x["rejection_count"]), str(x["sku"])),
    )

    return {
        "run_id": str(run_id),
        "entity": run.entity.value,
        "file_name": run.file_name,
        "status": run.status.value,
        "total_rejections": len(rejs),
        "by_reason": by_reason,
        "demand_sku_not_found": sku_nf_rows,
        "demand_insufficient_history": insuf_rows,
        "hints": {
            "sku_not_found": (
                "Each value is the SKU text from your file after sku_code_map. "
                "Fix by adding an active product with that SKU, importing Product Master, "
                "or adding a sku_code_map row (old_sku → new_sku) for the week range."
            ),
            "insufficient_history": (
                "Series were dropped because fewer than the minimum weeks of history exist "
                "for that SKU × warehouse × demand_type. Add more historical weeks or "
                "adjust policy in weekly_series_builder (MIN_WEEKS_HISTORY)."
            ),
        },
    }


def iter_rejection_csv_rows(db: Session, run_id: UUID) -> list[list[str]]:
    """Flat export rows: row_number, reason, raw_payload_json."""
    rejs = (
        db.query(IngestionRejection)
        .filter(IngestionRejection.ingestion_run_id == run_id)
        .order_by(IngestionRejection.id)
        .all()
    )
    out: list[list[str]] = []
    for r in rejs:
        payload = r.raw_payload
        try:
            payload_s = json.dumps(payload, default=str) if payload is not None else ""
        except TypeError:
            payload_s = str(payload)
        out.append([str(cast(int, r.row_number)), cast(str, r.reason), payload_s])
    return out
