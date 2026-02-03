"""Initial schema: products, warehouses, suppliers, lanes, planning_policy, inventory, receipts, demand, plan_runs, projected_inventory, planned_orders

Revision ID: 001
Revises:
Create Date: 2025-02-03

"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)

    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
    )
    op.create_index("ix_warehouses_code", "warehouses", ["code"], unique=True)

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
    )
    op.create_index("ix_suppliers_code", "suppliers", ["code"], unique=True)

    op.create_table(
        "lanes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
    )

    op.create_table(
        "planning_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("mode", sa.Enum("WOS_TARGET", "ROP", name="planningmode"), nullable=True),
        sa.Column("target_weeks", sa.Numeric(10, 2), nullable=True),
        sa.Column("safety_stock_method", sa.Enum("WEEKS", "SERVICE_LEVEL", name="safetystockmethod"), nullable=True),
        sa.Column("safety_stock_weeks", sa.Numeric(10, 2), nullable=True),
        sa.Column("service_level", sa.Numeric(5, 4), nullable=True),
        sa.Column("forecast_window_weeks", sa.Integer(), nullable=True),
        sa.Column("lead_time_production_weeks", sa.Numeric(10, 2), nullable=True),
        sa.Column("lead_time_slot_wait_weeks", sa.Numeric(10, 2), nullable=True),
        sa.Column("lead_time_haulage_weeks", sa.Numeric(10, 2), nullable=True),
        sa.Column("lead_time_putaway_weeks", sa.Numeric(10, 2), nullable=True),
        sa.Column("lead_time_padding_weeks", sa.Numeric(10, 2), nullable=True),
        sa.UniqueConstraint("sku", "warehouse_code", name="uq_planning_policy_sku_wh"),
    )
    op.create_index("ix_planning_policies_sku", "planning_policies", ["sku"])
    op.create_index("ix_planning_policies_warehouse_code", "planning_policies", ["warehouse_code"])

    op.create_table(
        "inventory_snapshots_weekly",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("on_hand_qty", sa.Numeric(18, 4), nullable=True),
        sa.UniqueConstraint("week_start", "sku", "warehouse_code", name="uq_inv_week_sku_wh"),
    )
    op.create_index("ix_inventory_snapshots_weekly_week_start", "inventory_snapshots_weekly", ["week_start"])
    op.create_index("ix_inventory_snapshots_weekly_sku", "inventory_snapshots_weekly", ["sku"])
    op.create_index("ix_inventory_snapshots_weekly_warehouse_code", "inventory_snapshots_weekly", ["warehouse_code"])

    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=True),
    )
    op.create_index("ix_receipts_week_start", "receipts", ["week_start"])
    op.create_index("ix_receipts_sku", "receipts", ["sku"])
    op.create_index("ix_receipts_warehouse_code", "receipts", ["warehouse_code"])

    op.create_table(
        "demand_actuals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("demand_type", sa.Enum("CUSTOMER", "SAMPLES", "ADJUSTMENT", name="demandtype"), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
    )
    op.create_index("ix_demand_actuals_week_start", "demand_actuals", ["week_start"])
    op.create_index("ix_demand_actuals_sku", "demand_actuals", ["sku"])
    op.create_index("ix_demand_actuals_warehouse_code", "demand_actuals", ["warehouse_code"])

    op.create_table(
        "plan_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scenario_name", sa.String(128), nullable=False),
        sa.Column("run_at", sa.Date(), nullable=False),
        sa.Column("created_at", sa.Date(), nullable=False),
    )
    op.create_index("ix_plan_runs_scenario_name", "plan_runs", ["scenario_name"])

    op.create_table(
        "projected_inventory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_run_id", sa.Integer(), sa.ForeignKey("plan_runs.id"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("projected_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("weeks_of_cover", sa.Numeric(10, 2), nullable=True),
        sa.Column("stockout", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_projected_inventory_plan_run_id", "projected_inventory", ["plan_run_id"])
    op.create_index("ix_projected_inventory_week_start", "projected_inventory", ["week_start"])
    op.create_index("ix_projected_inventory_sku", "projected_inventory", ["sku"])
    op.create_index("ix_projected_inventory_warehouse_code", "projected_inventory", ["warehouse_code"])

    op.create_table(
        "planned_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_run_id", sa.Integer(), sa.ForeignKey("plan_runs.id"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse_code", sa.String(32), nullable=False),
        sa.Column("order_qty", sa.Numeric(18, 4), nullable=False),
    )
    op.create_index("ix_planned_orders_plan_run_id", "planned_orders", ["plan_run_id"])
    op.create_index("ix_planned_orders_week_start", "planned_orders", ["week_start"])
    op.create_index("ix_planned_orders_sku", "planned_orders", ["sku"])
    op.create_index("ix_planned_orders_warehouse_code", "planned_orders", ["warehouse_code"])


def downgrade() -> None:
    op.drop_table("planned_orders")
    op.drop_table("projected_inventory")
    op.drop_table("plan_runs")
    op.drop_table("demand_actuals")
    op.drop_table("receipts")
    op.drop_table("inventory_snapshots_weekly")
    op.drop_table("planning_policies")
    op.drop_table("lanes")
    op.drop_table("suppliers")
    op.drop_table("warehouses")
    op.drop_table("products")
    op.execute("DROP TYPE IF EXISTS demandtype")
    op.execute("DROP TYPE IF EXISTS safetystockmethod")
    op.execute("DROP TYPE IF EXISTS planningmode")
