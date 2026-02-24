"""Backbone schema: calendar_weeks, supplier_products, warehouse_products, stock_positions_weekly, inbound_orders_weekly, demand_weekly, projections_weekly; alter warehouses/products/suppliers.

Revision ID: 003
Revises: 002
Create Date: 2025-02-03

"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Master data: add columns ---
    op.add_column("warehouses", sa.Column("timezone", sa.String(64), nullable=True))
    op.execute("UPDATE warehouses SET timezone = 'Europe/London' WHERE timezone IS NULL")
    op.alter_column("warehouses", "timezone", nullable=False, server_default="Europe/London")
    op.add_column("warehouses", sa.Column("active", sa.Boolean(), nullable=True))
    op.execute("UPDATE warehouses SET active = true WHERE active IS NULL")
    op.alter_column("warehouses", "active", nullable=False, server_default=sa.true())

    op.add_column("products", sa.Column("uom", sa.String(32), nullable=True))
    op.execute("UPDATE products SET uom = 'units' WHERE uom IS NULL")
    op.alter_column("products", "uom", nullable=False, server_default="units")
    op.add_column("products", sa.Column("active", sa.Boolean(), nullable=True))
    op.execute("UPDATE products SET active = true WHERE active IS NULL")
    op.alter_column("products", "active", nullable=False, server_default=sa.true())

    op.add_column("suppliers", sa.Column("active", sa.Boolean(), nullable=True))
    op.execute("UPDATE suppliers SET active = true WHERE active IS NULL")
    op.alter_column("suppliers", "active", nullable=False, server_default=sa.true())

    # --- calendar_weeks ---
    op.create_table(
        "calendar_weeks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("iso_year", sa.Integer(), nullable=False),
        sa.Column("iso_week", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("week_end_date", sa.Date(), nullable=False),
        sa.UniqueConstraint("iso_year", "iso_week", name="uq_calendar_weeks_iso"),
    )
    op.create_index("ix_calendar_weeks_iso_year_iso_week", "calendar_weeks", ["iso_year", "iso_week"])

    # --- supplier_products ---
    op.create_table(
        "supplier_products",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("lead_time_weeks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("moq_units", sa.Integer(), nullable=True),
        sa.Column("pack_size_units", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("supplier_id", "product_id", name="uq_supplier_products_supplier_product"),
    )
    op.create_index("ix_supplier_products_supplier_id", "supplier_products", ["supplier_id"])
    op.create_index("ix_supplier_products_product_id", "supplier_products", ["product_id"])

    # --- warehouse_products ---
    op.execute(
        "DO $$ BEGIN CREATE TYPE safety_stock_mode_enum AS ENUM ('fixed_units', 'fixed_weeks');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    op.execute(
        "CREATE TABLE warehouse_products ("
        " id SERIAL PRIMARY KEY,"
        " warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),"
        " product_id INTEGER NOT NULL REFERENCES products(id),"
        " safety_stock_mode safety_stock_mode_enum NOT NULL DEFAULT 'fixed_units',"
        " safety_stock_units INTEGER,"
        " safety_stock_weeks NUMERIC(10,2),"
        " haulage_buffer_weeks INTEGER NOT NULL DEFAULT 0,"
        " stocking_buffer_weeks INTEGER NOT NULL DEFAULT 0,"
        " reorder_review_weeks INTEGER NOT NULL DEFAULT 1,"
        " active BOOLEAN NOT NULL DEFAULT true,"
        " CONSTRAINT uq_warehouse_products_wh_product UNIQUE (warehouse_id, product_id)"
        ")"
    )
    op.create_index("ix_warehouse_products_warehouse_id", "warehouse_products", ["warehouse_id"])
    op.create_index("ix_warehouse_products_product_id", "warehouse_products", ["product_id"])

    # --- stock_positions_weekly ---
    op.execute(
        "DO $$ BEGIN CREATE TYPE stock_source_enum AS ENUM ('import', 'manual');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    op.execute(
        "CREATE TABLE stock_positions_weekly ("
        " id SERIAL PRIMARY KEY,"
        " warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),"
        " product_id INTEGER NOT NULL REFERENCES products(id),"
        " calendar_week_id INTEGER NOT NULL REFERENCES calendar_weeks(id),"
        " on_hand_units INTEGER NOT NULL DEFAULT 0,"
        " source stock_source_enum NOT NULL DEFAULT 'import',"
        " created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),"
        " CONSTRAINT uq_stock_positions_wh_product_week UNIQUE (warehouse_id, product_id, calendar_week_id)"
        ")"
    )
    op.create_index("ix_stock_positions_weekly_wh_product_week", "stock_positions_weekly", ["warehouse_id", "product_id", "calendar_week_id"], unique=True)

    # --- inbound_orders_weekly ---
    op.execute(
        "DO $$ BEGIN CREATE TYPE inbound_source_enum AS ENUM ('import', 'manual');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    op.execute(
        "CREATE TABLE inbound_orders_weekly ("
        " id SERIAL PRIMARY KEY,"
        " warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),"
        " product_id INTEGER NOT NULL REFERENCES products(id),"
        " supplier_id INTEGER REFERENCES suppliers(id),"
        " calendar_week_id INTEGER NOT NULL REFERENCES calendar_weeks(id),"
        " inbound_units INTEGER NOT NULL DEFAULT 0,"
        " source inbound_source_enum NOT NULL DEFAULT 'import',"
        " created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
        ")"
    )
    op.create_index("ix_inbound_orders_weekly_wh_product_week", "inbound_orders_weekly", ["warehouse_id", "product_id", "calendar_week_id"])

    # --- demand_weekly ---
    op.execute(
        "DO $$ BEGIN CREATE TYPE demand_source_enum AS ENUM ('import', 'manual', 'forecast');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    op.execute(
        "CREATE TABLE demand_weekly ("
        " id SERIAL PRIMARY KEY,"
        " warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),"
        " product_id INTEGER NOT NULL REFERENCES products(id),"
        " calendar_week_id INTEGER NOT NULL REFERENCES calendar_weeks(id),"
        " demand_units INTEGER NOT NULL DEFAULT 0,"
        " source demand_source_enum NOT NULL DEFAULT 'import',"
        " created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),"
        " CONSTRAINT uq_demand_weekly_wh_product_week UNIQUE (warehouse_id, product_id, calendar_week_id)"
        ")"
    )
    op.create_index("ix_demand_weekly_wh_product_week", "demand_weekly", ["warehouse_id", "product_id", "calendar_week_id"], unique=True)

    # --- projections_weekly ---
    op.execute(
        "DO $$ BEGIN CREATE TYPE breach_status_enum AS ENUM ('green', 'amber', 'red');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    op.execute(
        "CREATE TABLE projections_weekly ("
        " id SERIAL PRIMARY KEY,"
        " warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),"
        " product_id INTEGER NOT NULL REFERENCES products(id),"
        " calendar_week_id INTEGER NOT NULL REFERENCES calendar_weeks(id),"
        " opening_units INTEGER NOT NULL,"
        " inbound_units INTEGER NOT NULL,"
        " demand_units INTEGER NOT NULL,"
        " closing_units INTEGER NOT NULL,"
        " weeks_of_supply NUMERIC(12,4),"
        " safety_stock_target_units INTEGER NOT NULL,"
        " breach_status breach_status_enum NOT NULL,"
        " generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),"
        " run_id VARCHAR(36) NOT NULL,"
        " CONSTRAINT uq_projections_run_wh_product_week UNIQUE (run_id, warehouse_id, product_id, calendar_week_id)"
        ")"
    )
    op.create_index("ix_projections_weekly_run_id", "projections_weekly", ["run_id"])
    op.create_index("ix_projections_weekly_wh_product_week", "projections_weekly", ["warehouse_id", "product_id", "calendar_week_id"])


def downgrade() -> None:
    op.drop_table("projections_weekly")
    op.execute("DROP TYPE IF EXISTS breach_status_enum CASCADE")
    op.drop_table("demand_weekly")
    op.execute("DROP TYPE IF EXISTS demand_source_enum CASCADE")
    op.drop_table("inbound_orders_weekly")
    op.execute("DROP TYPE IF EXISTS inbound_source_enum CASCADE")
    op.drop_table("stock_positions_weekly")
    op.execute("DROP TYPE IF EXISTS stock_source_enum CASCADE")
    op.drop_table("warehouse_products")
    op.execute("DROP TYPE IF EXISTS safety_stock_mode_enum CASCADE")
    op.drop_table("supplier_products")
    op.drop_table("calendar_weeks")
    op.drop_column("suppliers", "active")
    op.drop_column("products", "active")
    op.drop_column("products", "uom")
    op.drop_column("warehouses", "active")
    op.drop_column("warehouses", "timezone")
