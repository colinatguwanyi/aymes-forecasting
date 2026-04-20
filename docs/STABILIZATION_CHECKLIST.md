# Platform stabilization checklist

Use this after merges and before calling the stack “production ready”. Check items off as you complete them.

---

## Where we are (snapshot)

| Area | State |
|------|--------|
| **Git** | `master` aligned with `origin/master`; merge commit `6388633` integrates backbone + forecasting/auth/ingestion work. |
| **Platform DB** | ORM uses portable **`JSON`** / **`Uuid`** (works with MySQL, Postgres, SQLite for dev). Default **`DATABASE_URL`** in code is **`mysql+pymysql://…`**; override via `.env`. |
| **Second DB** | **MySQL** for sales source (`MYSQL_*`) and forecast subsystem (`MYSQL_FORECAST_DATABASE`, `mysql_forecast_db`). |
| **Alembic** | Revisions **`001`–`024`** present; many revisions still emit **Postgres-specific** types/SQL (`JSONB`, `UUID`, `SERIAL`, raw `::jsonb`). Treat **“upgrade head on MySQL”** as unproven until you run it on a clone or add MySQL-safe revisions. |
| **Docs** | `CURRENT_BUILD_AND_SCHEMA.md` still describes **PostgreSQL** in places — update when you lock the platform DB story. |
| **Tests** | **~150 passing**, **~15 failing** (environment-dependent: real DB vs SQLite, demo-data guard, fixtures). Goal: deterministic CI profile (see below). |
| **Repo hygiene** | **`backend/app.zip`** and **`frontend/src.zip`** were merged; consider removing from git history or `.gitignore` if accidental. |
| **Frontend** | Vue 3 + Vite; large admin/forecast surface. Run **`npm run build`** after dependency or router changes. |

---

## 1. Configuration & secrets

- [ ] **`backend/.env`** (never commit): `DATABASE_URL`, `MYSQL_*`, optional `LEGACY_OUTPUT_*`, auth/bootstrap vars documented in `.env.example`.
- [ ] **`.env.example`** matches what new developers need (MySQL URL first; Postgres as optional legacy).
- [ ] **Single source of truth** for “platform” DB vs “forecast” DB vs “sales” DB — document in one place (README or `CURRENT_BUILD_AND_SCHEMA.md`).

## 2. Database & migrations

- [ ] **Prove `alembic upgrade head`** on the **target** platform (MySQL 8 if that is canonical), on an empty DB; fix or branch migrations if DDL fails.
- [ ] **Prove downgrade path** (at least one revision back) or document “forward-only” policy.
- [ ] **Align Alembic with MySQL** (follow-up): replace or gate Postgres-only constructs (`postgresql.JSONB`, `UUID` type, `SERIAL`, `::jsonb`) behind dialect checks or add parallel MySQL revisions.
- [ ] **Seed / demo**: decide `ALLOW_DEMO_DATA`, seed scripts, and how CI uses them.

## 3. Backend runtime

- [ ] **`python -c "from app.main import app"`** succeeds with production-like `.env`.
- [ ] **OpenAPI** (`/docs`) loads; smoke a critical path: auth (if enabled), products, one plan or import flow.
- [ ] **Remove or quarantine** leftover **Postgres-only** assumptions in services (naming like `pg_db` is OK if it’s still the SQLAlchemy session to the platform DB — rename later for clarity).

## 4. Tests & CI

- [ ] **`pytest`** green on a **defined** profile: e.g. SQLite for fast unit tests + optional integration job against MySQL/Postgres.
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

- [ ] **Decide Postgres drivers**: keep `psycopg2-binary` / `asyncpg` only if you still run Postgres anywhere; otherwise remove in a dedicated cleanup commit.
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
| **Backend** | Postgres 16 service → `pip install` → **`alembic upgrade head`** → **`pytest`**. |

**Important:** CI uses **`postgresql+psycopg2://…`** because current Alembic revisions are **PostgreSQL-oriented** (raw SQL, `JSONB`, etc.). That matches “migrations work today” and keeps the pipeline honest. Moving the **canonical** platform DB to MySQL still requires **MySQL-safe migrations** (or a new branch of revisions); until then, treat **Postgres + Alembic** as the verified migration path in CI.

**Local quick checks**

- **SQLite** is a poor fit for this migration chain (e.g. revision **002** uses constraint changes SQLite cannot `ALTER` without batch mode). Do not rely on `alembic upgrade head` on SQLite.
- **MySQL**: revisions such as **004** use Postgres-only DDL (`DO $$ …`, `gen_random_uuid()`, etc.); expect failures until migrations are ported.

Env vars in CI: `ALLOW_DEMO_DATA=true` so planning tests that touch demo SKUs are not blocked by the demo-data guard.

---

## Definition of “stabilised” (suggested)

1. CI green: **tests + frontend build**.  
2. **Fresh DB** + **`alembic upgrade head`** documented and verified on target engine.  
3. **No merge conflict markers**; no stray binaries unless justified.  
4. **Docs** describe actual DB URLs and environments.
