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
```

## 4. Migrations

From `backend/`:

```bash
pip install -r requirements.txt
alembic upgrade head
```

Baseline revision **`001_mysql_baseline`** creates all tables from the SQLAlchemy models (`create_all`).

## 5. Optional seed data

With `ALLOW_DEMO_DATA=true` in `.env`, you can run `python -m app.seed` or `python -m app.seed_backbone` for local demo content.

## Troubleshooting

- **`Can't connect to MySQL server` / connection refused** — MySQL is not running or not on port 3306. Start the service or the Docker container above.
- **Alembic shows `SQLiteImpl` but you use MySQL** — A shell or tool may have set `DATABASE_URL` (for example to a smoke-test SQLite file). That overrides `backend/.env`. In PowerShell: `Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue`, then run `alembic` again from `backend/`.
