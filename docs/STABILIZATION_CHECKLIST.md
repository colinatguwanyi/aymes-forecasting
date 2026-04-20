# Platform stabilization checklist

Use this after merges and before calling the stack “production ready”. Check items off as you complete them.

---

## Where we are (snapshot)

| Area | State |
|------|--------|
| **Git** | `master` aligned with `origin/master`; merge commit `6388633` integrates backbone + forecasting/auth/ingestion work. |
| **Platform DB** | **MySQL 8** only. ORM uses **`JSON`** / **`Uuid`**. Default **`DATABASE_URL`** is **`mysql+pymysql://…?charset=utf8mb4`**; override via `.env`. |
| **Second DB** | **MySQL** for sales source (`MYSQL_*`) and forecast subsystem (`MYSQL_FORECAST_DATABASE`, `mysql_forecast_db`). |
| **Alembic** | **MySQL-only** baseline: **`001_mysql_baseline`** creates the full platform schema from ORM metadata (`create_all`). Older Postgres revisions were removed; use git history if you need legacy DDL. |
| **Docs** | Platform DB documented as MySQL in README / `MYSQL_SETUP.md` / `CURRENT_BUILD_AND_SCHEMA.md`. |
| **Tests** | **~150 passing**, **~15 failing** (environment-dependent: real DB vs SQLite, demo-data guard, fixtures). Goal: deterministic CI profile (see below). |
| **Repo hygiene** | **`backend/app.zip`** and **`frontend/src.zip`** were merged; consider removing from git history or `.gitignore` if accidental. |
| **Frontend** | Vue 3 + Vite; large admin/forecast surface. Run **`npm run build`** after dependency or router changes. |

---

## 1. Configuration & secrets

- [ ] **`backend/.env`** (never commit): `DATABASE_URL`, `MYSQL_*`, optional `LEGACY_OUTPUT_*`, auth/bootstrap vars documented in `.env.example`.
- [ ] **`.env.example`** matches what new developers need (MySQL `DATABASE_URL` only).
- [ ] **Single source of truth** for “platform” DB vs “forecast” DB vs “sales” DB — document in one place (README or `CURRENT_BUILD_AND_SCHEMA.md`).

## 2. Database & migrations

- [ ] **Prove `alembic upgrade head`** on an **empty MySQL 8** database (CI does this).
- [ ] **Prove downgrade path** (`drop_all` in `001_mysql_baseline` downgrade) or document “forward-only” policy for production.
- [ ] **Seed / demo**: decide `ALLOW_DEMO_DATA`, seed scripts, and how CI uses them.

## 3. Backend runtime

- [ ] **`python -c "from app.main import app"`** succeeds with production-like `.env`.
- [ ] **OpenAPI** (`/docs`) loads; smoke a critical path: auth (if enabled), products, one plan or import flow.
- [ ] **Remove or quarantine** leftover **Postgres-only** assumptions in services (naming like `pg_db` is OK if it’s still the SQLAlchemy session to the platform DB — rename later for clarity).

## 4. Tests & CI

- [ ] **`pytest`** green on a **defined** profile (CI: MySQL 8 + `alembic upgrade head`).
- [ ] Fix or **skip with reason** tests that require a live DB when run without it (`warehouse_scope`, `demand_warehouse_separation`, etc.).
- [ ] Add **GitHub Actions / CI** (or equivalent): lint, `pytest`, `npm run build`.
- [ ] **Pyright/ruff** (if used): align `pyrightconfig.json` with CI.

## 5. Frontend

- [ ] **`npm ci`** / **`npm install`** reproducible (`package-lock.json` committed).
- [ ] **`npm run build`** passes (no Vue/TS errors).
- [ ] **API base URL** correct for dev (`vite` proxy or `client.ts` env).

## 6. Security & auth

- [ ] **RBAC / dev auth**: `DEV_DEFAULT_USER_EMAIL`, `X-Dev-User`, Entra — behaviour documented for each environment.
- [ ] **Router dependencies** (`require_any_auth`, `require_admin_or_planner`, etc.) reviewed for public vs protected routes.

## 7. Dependencies

- [x] **Postgres drivers removed** from `requirements.txt` (platform DB is MySQL only).
- [ ] **Pin** risky deps (Prophet, xgboost) or document platform requirements (build tools, OS).

## 8. Repository cleanup

- [ ] Remove **`*.zip`** artifacts from tracking if not intentional (`git rm --cached` + `.gitignore`).
- [ ] Ensure **`__pycache__`**, **`venv/`**, **`node_modules/`**, **`frontend/dist/`** are not tracked (`.gitignore` already lists most).
- [ ] **Update docs** (`CURRENT_BUILD_AND_SCHEMA.md`, `FORECASTING_PLATFORM_SPEC.md`) to match **MySQL-first** platform DB and dual-DB architecture.

## 9. Operational readiness

- [ ] **Backup / restore** procedure for platform DB and forecast MySQL DB.
- [ ] **Health check** endpoint or load-balancer probe (if deployed).
- [ ] **Logging**: structured logs, no secrets in logs.

---

## Continuous integration (enabled)

GitHub Actions workflow: **`.github/workflows/ci.yml`**

| Job | What it does |
|-----|----------------|
| **Frontend** | `npm ci` + `npm run build` (Node 20). |
| **Backend** | MySQL 8.0 service → `pip install` → **`alembic upgrade head`** → **`pytest`**. |

CI **`DATABASE_URL`**: `mysql+pymysql://root:root@127.0.0.1:3306/supply_planning?charset=utf8mb4`.

**Local quick checks**

- Use **MySQL 8** for the platform DB; run `alembic upgrade head` against an empty schema.
- **SQLite** is still a weak fit for many integration tests; use **MySQL 8** locally to match CI.

Env vars in CI: `ALLOW_DEMO_DATA=true` so planning tests that touch demo SKUs are not blocked by the demo-data guard.

---

## Definition of “stabilised” (suggested)

1. CI green: **tests + frontend build**.  
2. **Fresh DB** + **`alembic upgrade head`** documented and verified on target engine.  
3. **No merge conflict markers**; no stray binaries unless justified.  
4. **Docs** describe actual DB URLs and environments.
