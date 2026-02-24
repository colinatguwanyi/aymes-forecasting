# PostgreSQL setup for Aymes Forecasting

This guide walks through setting up PostgreSQL from scratch and connecting the app.

---

## 1. Install PostgreSQL (if not already)

- **Windows**: Download from [postgresql.org/download/windows](https://www.postgresql.org/download/windows/) or use the installer. During setup you’ll set a password for the `postgres` user (e.g. `postgres`).
- **macOS**: `brew install postgresql@14` (or 15/16), then start: `brew services start postgresql@14`.
- **Linux**: e.g. `sudo apt install postgresql postgresql-client` (Debian/Ubuntu).

Ensure the PostgreSQL service is running (e.g. port **5432**).

---

## 2. Create a database and (optional) app user

You can use the default `postgres` user or create a dedicated user and database.

### Option A – Use default `postgres` user (simplest)

1. Open a shell and connect as the superuser:
   - **Windows**: From “SQL Shell (psql)” in the Start menu, or `psql -U postgres` from a terminal if `psql` is on PATH.
   - **macOS/Linux**: `psql -U postgres` (or `psql postgres`).

2. Create the database:
   ```sql
   CREATE DATABASE supply_planning;
   ```
3. Optional: set a password for `postgres` if you haven’t:
   ```sql
   ALTER USER postgres PASSWORD 'postgres';
   ```
4. Exit: `\q`

### Option B – Dedicated user and database

In `psql -U postgres`:

```sql
CREATE USER supply_planning_user WITH PASSWORD 'your_password';
CREATE DATABASE supply_planning OWNER supply_planning_user;
GRANT ALL PRIVILEGES ON DATABASE supply_planning TO supply_planning_user;
\q
```

Then use:
`postgresql://supply_planning_user:your_password@localhost:5432/supply_planning`
in the app (see step 4).

---

## 3. Confirm the database exists

From the OS shell:

```bash
psql -U postgres -l
```

You should see `supply_planning` in the list.

---

## 4. Configure the app (backend)

The app reads the connection string from the **`DATABASE_URL`** environment variable (or `.env` in the backend folder).

1. Go to the backend directory:
   ```bash
   cd backend
   ```

2. Copy the example env file and edit if needed:
   ```bash
   copy .env.example .env
   ```
   (On macOS/Linux: `cp .env.example .env`.)

3. Open `.env`. It should contain something like:
   ```env
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/supply_planning
   ```
   Format: `postgresql://USER:PASSWORD@HOST:PORT/DATABASE`

   - If you use a different user/password/database (e.g. from Option B), change `USER`, `PASSWORD`, and `DATABASE` accordingly.
   - If Postgres is on another host or port, change `HOST` and `PORT`.

---

## 5. Install Python deps and run migrations

From the **backend** directory, use a **virtual environment** (recommended on Windows to avoid “Could not install packages” / `websockets.exe` errors when installing to system Python):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
```

If you don’t use a venv and see `OSError` or `WinError 2` when installing, create and use the venv as above, then run the same `pip install` and `alembic` commands inside it.

- `alembic upgrade head` applies all migrations and creates/updates tables (warehouses, products, calendar_weeks, projections_weekly, etc.).
- If you see “connection refused”, Postgres isn’t running or `DATABASE_URL` (host/port/user/password) is wrong.

---

## 6. Seed demo data (optional but recommended)

Backbone demo data (warehouses, products, suppliers, calendar weeks, warehouse-products, sample stock/demand):

```bash
python -m app.seed_backbone
```

Legacy seed (if you use older features):

```bash
python -m app.seed
```

---

## 7. Verify

1. Start the backend:
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. Open:
   - API docs: http://127.0.0.1:8000/docs  
   - Try e.g. `GET /api/warehouses` or `GET /api/products` — you should get data if you ran `seed_backbone`.

3. If the app fails at startup with a DB error, check:
   - Postgres is running.
   - `DATABASE_URL` in `.env` matches your server (user, password, host, port, database name).
   - The database exists (`psql -U postgres -l`).

---

## Quick reference

| Step              | Command / action                                      |
|-------------------|--------------------------------------------------------|
| Create DB         | `createdb -U postgres supply_planning` or `CREATE DATABASE` in psql |
| Backend config    | `backend/.env` with `DATABASE_URL=postgresql://...`     |
| Migrations        | `cd backend && alembic upgrade head`                    |
| Seed (backbone)   | `cd backend && python -m app.seed_backbone`            |
| Run API           | `cd backend && uvicorn app.main:app --reload --port 8000` |

Default URL used by the app if `.env` is missing:
`postgresql://postgres:postgres@localhost:5432/supply_planning`
