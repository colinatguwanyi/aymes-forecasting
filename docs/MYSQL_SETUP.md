# MySQL 8 — platform database

The planning platform uses **MySQL 8** as the only supported database for `DATABASE_URL`.

## 1. Install MySQL 8

- **Windows**: [MySQL Installer](https://dev.mysql.com/downloads/installer/) or your package manager.
- **macOS**: `brew install mysql` and start the service.
- **Linux**: `sudo apt install mysql-server` (Debian/Ubuntu) or your distro equivalent.

Ensure the server listens on **3306** (or note your port).

### Docker (quick local)

If you use Docker, you can run MySQL 8 without a host install:

```bash
docker run -d --name aymes-mysql -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=devroot \
  -e MYSQL_DATABASE=supply_planning \
  -e MYSQL_USER=aymes \
  -e MYSQL_PASSWORD=devpass \
  mysql:8
```

Then set `DATABASE_URL` to:

`mysql+pymysql://aymes:devpass@127.0.0.1:3306/supply_planning?charset=utf8mb4`

## 2. Create database and user

```sql
CREATE DATABASE supply_planning CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'aymes'@'%' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON supply_planning.* TO 'aymes'@'%';
FLUSH PRIVILEGES;
```

## 3. Configure the backend

In `backend/.env` (see `.env.example`):

```env
DATABASE_URL=mysql+pymysql://aymes:your_password@localhost:3306/supply_planning?charset=utf8mb4
# If the API returns 503 / “Database unavailable” but `mysql` CLI works, try:
# DATABASE_SSL_DISABLED=true
```

The forecast engine uses the **same MySQL host, port, user, and password** as **`DATABASE_URL`**. By default it uses the **same database name** as `DATABASE_URL` too (e.g. `supply_planning`), so you do not need a second `GRANT` or a separate `aymes_forecasting` database unless you set `MYSQL_FORECAST_DATABASE` yourself.

For legacy/ingest code that still reads `MYSQL_*`, if you omit `MYSQL_PASSWORD` (or leave it empty), the backend fills `MYSQL_USER` / `MYSQL_PASSWORD` / host / port from `DATABASE_URL` when possible.

### Admin Forecast Engine — sales source without `aymes_reports`

If your MySQL only has **`supply_planning`** (and no `aymes_reports`), the Sales Grid and **`demand_facts_weekly`** already hold canonical weekly customer demand. For **Forecast v2 → Execute (ingest)**, set the **source config** to:

- **mysql_database** = same as `DATABASE_URL` (e.g. `supply_planning`)
- **mysql_sales_table** = `demand_facts_weekly`
- **mysql_host** = leave blank or match `DATABASE_URL` (localhost / 127.0.0.1 are treated as equivalent)

Ingest then reads **`CUSTOMER`** rows from `demand_facts_weekly` via the platform connection (same data as the Sales Grid), not the legacy `adhl_data_daily` shape.

## 4. Migrations

From `backend/`:

```bash
pip install -r requirements.txt
alembic upgrade head
```

Baseline revision **`001_mysql_baseline`** creates platform tables from `app.models` / `app.database.Base`.

**Important:** revision **`004_forecast_engine_mysql`** drops legacy `forecast_*` tables that 001 created from `app.forecast_models` (incompatible columns) and creates the **Admin Forecast Engine** schema from `app.forecast_mysql_models` in the same database as `DATABASE_URL`. Run `alembic upgrade head` so 004 is applied.

If you cannot use Alembic, you can create the engine schema manually (same DB as `DATABASE_URL` unless `MYSQL_FORECAST_DATABASE` is set):

```bash
cd backend
python -c "from app.services.forecasting.mysql_forecast_db import init_forecast_schema; init_forecast_schema()"
```

If you use a separate `MYSQL_FORECAST_DATABASE`, create that database and `GRANT` your user on it first, then upgrade or run the command above (or apply `backend/mysql/forecast_schema.sql`).

## 5. Optional seed data

With `ALLOW_DEMO_DATA=true` in `.env`, you can run `python -m app.seed` or `python -m app.seed_backbone` for local demo content.

## Troubleshooting

- **`Can't connect to MySQL server` / connection refused** — MySQL is not running or not on port 3306. Start the service or the Docker container above.
- **Alembic shows `SQLiteImpl` but you use MySQL** — A shell or tool may have set `DATABASE_URL` (for example to a smoke-test SQLite file). That overrides `backend/.env`. In PowerShell: `Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue`, then run `alembic` again from `backend/`.
- **`1044` … Access denied … to database `aymes_forecasting`** — The user can log in but has no rights on that database. Either run `GRANT ALL ON aymes_forecasting.* …`, or remove `MYSQL_FORECAST_DATABASE` from `.env` so the app uses the same database as `DATABASE_URL`, then run `init_forecast_schema` (see section 4).
- **`1054` … Unknown column `source_name` / `config_name` on `forecast_*`** — The database still has the **old** `forecast_models` / 001-baseline table layout. Run `alembic upgrade head` so revision **`004_forecast_engine_mysql`** replaces those tables with the engine schema (or drop the old `forecast_*` tables and run `init_forecast_schema()`).
- **Forecast sales ingest: `1044` … Access denied for user '…' to database `aymes_reports`** — The same MySQL user in `DATABASE_URL` can use `supply_planning` (platform) but has **no rights** on `aymes_reports` (where `adhl_data_daily` usually lives). As MySQL `root` or an admin, run e.g. `GRANT SELECT ON aymes_reports.* TO 'aymes'@'localhost';` and the same for `'aymes'@'127.0.0.1'` if your app connects with that host, then `FLUSH PRIVILEGES;`. Use your real username from `DATABASE_URL` instead of `aymes` if different.
