"""
Standard keys for IngestionRun.progress_meta during long-running imports (frontend polls GET /ingestion/runs/{id}).

- import_version: schema version (1)
- import_phase: short machine id (e.g. soh_daily, sales_out_write, demand_transform)
- import_message: primary line for the user
- import_detail: optional secondary line
- import_percent: 0–100 when known, omitted for indeterminate
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import IngestionRun

logger = logging.getLogger(__name__)

IMPORT_PROGRESS_VERSION = 1


def merge_ingest_progress(
    db: Session,
    run: IngestionRun,
    *,
    import_phase: str,
    import_message: str,
    import_percent: float | int | None = None,
    import_detail: str | None = None,
    **extra: Any,
) -> None:
    """
    Merge standard + extra keys into progress_meta and **commit** so other HTTP requests
    (e.g. polling) see progress while this request continues.
    """
    _pm = getattr(run, "progress_meta", None)
    base: dict[str, Any] = dict(_pm) if isinstance(_pm, dict) else {}
    base["import_version"] = IMPORT_PROGRESS_VERSION
    base["import_phase"] = import_phase
    base["import_message"] = import_message
    if import_percent is not None:
        try:
            base["import_percent"] = max(0.0, min(100.0, float(import_percent)))
        except (TypeError, ValueError):
            base["import_percent"] = None
    if import_detail is not None:
        base["import_detail"] = import_detail
    for k, v in extra.items():
        base[k] = v
    run.progress_meta = base
    db.commit()
    try:
        db.refresh(run)
    except Exception as exc:  # pragma: no cover
        logger.debug("ingestion_progress refresh after commit: %s", exc)
