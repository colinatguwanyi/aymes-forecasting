"""Single source of truth: week-by-week projection calculation. Persist to projections_weekly."""
from __future__ import annotations
import logging
import math
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Optional, cast

from sqlalchemy.orm import Session

from app.calendar_weeks import ensure_calendar_week, week_start_end
from app.models import (
    BreachStatusEnum,
    CalendarWeek,
    DemandWeekly,
    InboundOrderWeekly,
    ProjectionWeekly,
    StockPositionWeekly,
    Warehouse,
    WarehouseProduct,
    SafetyStockModeEnum,
)

logger = logging.getLogger(__name__)

WOS_SENTINEL = 999.0  # when avg demand is 0, do not divide by zero


def run_projection(
    db: Session,
    warehouse_id: Optional[int] = None,
    start_iso_year: int = 2025,
    start_iso_week: int = 1,
    horizon_weeks: int = 26,
) -> str:
    """
    Generate projections for warehouse(s), horizon. Returns run_id.
    warehouse_id=None means all warehouses.
    """
    run_id = str(uuid.uuid4())
    warehouses = (
        db.query(Warehouse).filter(Warehouse.id == warehouse_id).all()
        if warehouse_id is not None
        else db.query(Warehouse).filter(Warehouse.active.is_(True)).all()
    )
    calendar_weeks: list[CalendarWeek] = []
    y, w = start_iso_year, start_iso_week
    for _ in range(horizon_weeks):
        cw = ensure_calendar_week(db, y, w)
        calendar_weeks.append(cw)
        w += 1
        if w > 52:
            w = 1
            y += 1

    for wh in warehouses:
        wp_list = (
            db.query(WarehouseProduct)
            .filter(WarehouseProduct.warehouse_id == wh.id, WarehouseProduct.active.is_(True))
            .all()
        )
        for wp in wp_list:
            product_id = wp.product_id
            warehouse_id_val = wh.id
            # Load stock positions for (wh, product) keyed by calendar_week_id
            stock_by_cw: dict[int, int] = {}
            for sp in (
                db.query(StockPositionWeekly)
                .filter(
                    StockPositionWeekly.warehouse_id == warehouse_id_val,
                    StockPositionWeekly.product_id == product_id,
                    StockPositionWeekly.calendar_week_id.in_([cw.id for cw in calendar_weeks]),
                )
                .all()
            ):
                cw_id = getattr(sp, "calendar_week_id")
                stock_by_cw[int(cw_id)] = int(getattr(sp, "on_hand_units"))

            inbound_by_cw: dict[int, int] = defaultdict(int)
            for io in (
                db.query(InboundOrderWeekly)
                .filter(
                    InboundOrderWeekly.warehouse_id == warehouse_id_val,
                    InboundOrderWeekly.product_id == product_id,
                    InboundOrderWeekly.calendar_week_id.in_([cw.id for cw in calendar_weeks]),
                )
                .all()
            ):
                cw_id_io = getattr(io, "calendar_week_id")
                inbound_by_cw[int(cw_id_io)] += int(getattr(io, "inbound_units"))

            demand_by_cw: dict[int, int] = {}
            for dw in (
                db.query(DemandWeekly)
                .filter(
                    DemandWeekly.warehouse_id == warehouse_id_val,
                    DemandWeekly.product_id == product_id,
                    DemandWeekly.calendar_week_id.in_([cw.id for cw in calendar_weeks]),
                )
                .all()
            ):
                cw_id_dw = getattr(dw, "calendar_week_id")
                demand_by_cw[int(cw_id_dw)] = int(getattr(dw, "demand_units"))

            opening = 0
            for idx, cw in enumerate(calendar_weeks):
                cw_id = getattr(cw, "id")
                if idx == 0:
                    opening = stock_by_cw.get(int(cw_id), 0)
                inbound = inbound_by_cw.get(int(cw_id), 0)
                demand = demand_by_cw.get(int(cw_id), 0)
                closing = opening + inbound - demand
                closing = max(0, closing)

                # Avg weekly demand for next 8 weeks (t..t+7) for WOS and safety stock
                demand_sum = 0
                for j in range(8):
                    if idx + j < len(calendar_weeks):
                        cw_j_id = getattr(calendar_weeks[idx + j], "id")
                        demand_sum += demand_by_cw.get(int(cw_j_id), 0)
                avg_demand_8 = demand_sum / 8.0 if demand_sum else 0.0

                safety_mode = cast(SafetyStockModeEnum, getattr(wp, "safety_stock_mode", None))
                safety_stock_units_val = cast(Optional[int], getattr(wp, "safety_stock_units", None))
                safety_stock_weeks_val = cast(Optional[Decimal], getattr(wp, "safety_stock_weeks", None))
                if safety_mode == SafetyStockModeEnum.FIXED_UNITS:
                    target_units = int(safety_stock_units_val or 0)
                else:
                    # fixed_weeks
                    weeks_val = float(safety_stock_weeks_val or 0)
                    target_units = int(math.ceil(avg_demand_8 * weeks_val)) if avg_demand_8 else 0

                if avg_demand_8 > 0:
                    wos_val = closing / avg_demand_8
                else:
                    wos_val = WOS_SENTINEL

                if closing < target_units:
                    breach = BreachStatusEnum.RED
                elif closing < target_units + (avg_demand_8 * 1):
                    breach = BreachStatusEnum.AMBER
                else:
                    breach = BreachStatusEnum.GREEN

                db.add(
                    ProjectionWeekly(
                        warehouse_id=warehouse_id_val,
                        product_id=product_id,
                        calendar_week_id=cw.id,
                        opening_units=opening,
                        inbound_units=inbound,
                        demand_units=demand,
                        closing_units=closing,
                        weeks_of_supply=Decimal(str(round(wos_val, 4))) if wos_val != WOS_SENTINEL else None,
                        safety_stock_target_units=target_units,
                        breach_status=breach,
                        run_id=run_id,
                    )
                )
                opening = closing

    db.commit()
    return run_id
