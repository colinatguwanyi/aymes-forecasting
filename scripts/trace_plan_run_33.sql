-- Phase A: Trace plan_run_id=33 and demo data sources
-- Run: psql -d <your_db> -f scripts/trace_plan_run_33.sql

\echo '=== 1) Projected inventory SKUs for plan_run_id=33 ==='
SELECT DISTINCT sku FROM projected_inventory WHERE plan_run_id=33 ORDER BY 1;

\echo ''
\echo '=== 2) Planned orders SKUs for plan_run_id=33 ==='
SELECT DISTINCT sku FROM planned_orders WHERE plan_run_id=33 ORDER BY 1;

\echo ''
\echo '=== 3) Demand actuals count for AAH ==='
SELECT COUNT(*) AS demand_actuals_aah_count FROM demand_actuals WHERE warehouse_code='AAH';

\echo ''
\echo '=== 4) Inventory snapshots count for AAH ==='
SELECT COUNT(*) AS inventory_snapshots_aah_count FROM inventory_snapshots_weekly WHERE warehouse_code='AAH';

\echo ''
\echo '=== 5) Distinct SKUs in demand_actuals for AAH (first 20) ==='
SELECT DISTINCT sku FROM demand_actuals WHERE warehouse_code='AAH' ORDER BY 1 LIMIT 20;

\echo ''
\echo '=== 6) Distinct SKUs in inventory_snapshots_weekly for AAH (first 20) ==='
SELECT DISTINCT sku FROM inventory_snapshots_weekly WHERE warehouse_code='AAH' ORDER BY 1 LIMIT 20;

\echo ''
\echo '=== 7) Products SKU1/SKU2/SKU3/SKU4 (demo check) ==='
SELECT sku, name FROM products WHERE sku IN ('SKU1','SKU2','SKU3','SKU4');

\echo ''
\echo '=== 8) Products SKU001/SKU002/SKU003/SKU004 (seed check) ==='
SELECT sku, name FROM products WHERE sku IN ('SKU001','SKU002','SKU003','SKU004');
