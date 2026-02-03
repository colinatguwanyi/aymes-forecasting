# Weekly Supply Planning MVP

MVP weekly supply planning system: Vue 3 (TypeScript) frontend, FastAPI backend, Postgres database.

## Standards

- **Python typing**: Follow [docs/TYPING_STANDARDS.md](docs/TYPING_STANDARDS.md) for all backend Python code (scaffolding, generics, return types, SQLAlchemy, Pyright).

## Core goal

For each SKU and warehouse, project weekly inventory forward and recommend planned orders based on admin-tunable parameters (lead times, safety stock, target weeks of supply). Separate demand streams (CUSTOMER, SAMPLES, ADJUSTMENT) so sample withdrawals do not distort forecasts.

## Quick start

### Prerequisites

- Python 3.11+
- Node 18+
- PostgreSQL 14+

### 1. Database

Create a database and run migrations:

```bash
createdb supply_planning
cd backend
pip install -r requirements.txt
# Set DATABASE_URL if different from postgresql://postgres:postgres@localhost:5432/supply_planning
alembic upgrade head
python -m app.seed
```

### 2. Backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://127.0.0.1:8000/docs

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` to the backend).

## Local build and deploy

Single-server deploy: build the frontend, then run the backend. The backend serves both the API and the built Vue app from `frontend/dist`.

1. **Build frontend**
   ```bash
   cd frontend
   npm install
   npm run build
   ```
   Output: `frontend/dist/`

2. **Run backend** (from project root or `backend/`)
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Open** http://localhost:8000 — app and API on one origin. API docs: http://localhost:8000/docs

Or run the script (build only; you still start uvicorn yourself):
- **Windows:** `.\scripts\build-and-deploy.ps1`
- **Linux/macOS:** `./scripts/build-and-deploy.sh`

Ensure Postgres is running and migrations are applied (see Quick start) before using the app.

## Folder structure

```
aymes-forecasting/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py         # SQLAlchemy models
│   │   ├── schemas.py        # Pydantic schemas
│   │   ├── seed.py           # Seed script
│   │   ├── routers/          # API routes
│   │   └── services/         # Planning + CSV import
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/              # API client
│   │   ├── router/
│   │   ├── stores/           # Pinia
│   │   └── views/            # Pages
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Features

- **Dashboard**: Stockout risk next 8/13 weeks, top SKUs by risk, run scenario.
- **Inventory Projection**: Table + chart by SKU/warehouse with scenario selector; compare two scenarios.
- **Planned Orders**: Exportable table and CSV export.
- **Admin**: Products, Warehouses, Suppliers, Lanes, Planning Policies (mode WOS_TARGET or ROP, target weeks, safety stock, forecast window, lead time components).
- **Imports**: CSV upload with dry-run validation and row error report; confirm import. Templates: inventory-snapshots, receipts, demand-actuals, samples-withdrawals, products.
- **Exports**: CSV for projected inventory and planned orders by scenario.

## API summary

- `GET/POST /api/products`, `/api/warehouses`, `/api/suppliers`, `/api/lanes`, `/api/planning-policies`
- `GET /api/inventory`, `/api/receipts`, `/api/demand`
- `POST /api/plan/run?scenario_name=...`
- `GET /api/plan/runs`, `/api/plan/runs/{id}/projected-inventory`, `/api/plan/runs/{id}/planned-orders`
- `POST /api/import/inventory-snapshots`, `/receipts`, `/demand-actuals`, `/samples-withdrawals`, `/products` (query `dry_run=true|false`, body: CSV file)
- `GET /api/exports/projected-inventory?plan_run_id=...`, `/api/exports/planned-orders?plan_run_id=...`
- `GET /api/templates/inventory-snapshots`, `/receipts`, `/demand-actuals`, `/samples-withdrawals`, `/products` (CSV template download)

## Week convention

All planning is week-based with **week_start = Monday** (YYYY-MM-DD). CSV dates must be Mondays.
