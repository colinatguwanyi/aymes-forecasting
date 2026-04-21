# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import settings
from app.database import Base, engine
from app.routers import (
    admin_forecast_methods,
    app_settings,
    auth,
    data_health,
    diagnostics,
    sales_reports,
    stock_coverage_reports,
    products,
    warehouses,
    suppliers,
    warehouse_products,
    supplier_products,
    backbone_imports,
    projections,
    backbone_reports,
    lanes,
    planning_policies,
    inventory,
    receipts,
    demand,
    plan_run,
    stock_position,
    timeline,
    imports_router,
    exports,
    templates,
    ingestion,
    forecast,
    forecast_v2,
    warehouse_product_codes,
    soh_reports,
)

logger = logging.getLogger(__name__)
# Uvicorn configures this logger at INFO — use it for startup messages users should see in the console.
_uvicorn_log = logging.getLogger("uvicorn.error")

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.warning(
        "Database not available at startup (%s). App will run but API will fail until the database is reachable.",
        e,
    )

# Path to built frontend (when running from backend/ or project root)
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
_ASSETS_DIR = _DIST / "assets"
# Require a full Vite build (index + assets). Partial dist/ (e.g. repo stub) must not mount — StaticFiles raises if missing.
_SERVE_FRONTEND = _DIST.is_dir() and (_DIST / "index.html").is_file() and _ASSETS_DIR.is_dir()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        host_part = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
        _uvicorn_log.info(
            "Database OK (ssl_disabled=%s, target=%s)",
            settings.database_ssl_disabled,
            host_part,
        )
    except Exception:
        logger.exception(
            "Database connection failed at startup. Fix MySQL / DATABASE_URL / DATABASE_SSL_DISABLED, then restart."
        )
    yield


app = FastAPI(
    title="Weekly Supply Planning API",
    description="MVP weekly supply planning with SKU/warehouse projections and planned orders",
    version="1.0.0",
    lifespan=_lifespan,
)

_DB_UNAVAILABLE = (
    "Database unavailable. Start MySQL 8, ensure DATABASE_URL in backend/.env is correct "
    "(mysql+pymysql://user:password@host:3306/supply_planning?charset=utf8mb4), then run "
    "`alembic upgrade head` from the backend folder. See docs/MYSQL_SETUP.md. "
    "If MySQL is up but you use a local Enterprise/installer build, try DATABASE_SSL_DISABLED=true in .env."
)


def _sqlalchemy_db_error_response(exc: OperationalError | ProgrammingError) -> JSONResponse:
    """503 for connection failures and common schema errors so the UI gets a clear message."""
    orig = getattr(exc, "orig", None)
    logger.warning("Database error (503): %s", exc, exc_info=True)
    detail: str = _DB_UNAVAILABLE
    if orig is not None and getattr(orig, "args", None):
        errno = orig.args[0] if orig.args else None
        if errno == 1205:
            detail = (
                "MySQL lock wait timeout (1205). Another session is holding a row lock — often Beekeeper "
                "(disable long transactions / turn on Auto Commit), a second browser tab running Execute, "
                "or a previous build still running. Close other DB clients, wait, then retry build-weekly once."
            )
            if settings.environment.lower() in ("dev", "local", "development"):
                detail = f"{detail} Server said: {orig!s}"
            return JSONResponse(status_code=503, content={"detail": detail})
    if settings.environment.lower() in ("dev", "local", "development") and orig is not None:
        detail = f"{_DB_UNAVAILABLE} Server said: {orig!s}"
    return JSONResponse(status_code=503, content={"detail": detail})


async def _sqlalchemy_operational_handler(_request: Request, exc: OperationalError) -> JSONResponse:
    return _sqlalchemy_db_error_response(exc)


async def _sqlalchemy_programming_handler(_request: Request, exc: ProgrammingError) -> JSONResponse:
    return _sqlalchemy_db_error_response(exc)


app.add_exception_handler(OperationalError, _sqlalchemy_operational_handler)  # pyright: ignore[reportArgumentType]
app.add_exception_handler(ProgrammingError, _sqlalchemy_programming_handler)  # pyright: ignore[reportArgumentType]


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(warehouses.router, prefix="/api/warehouses", tags=["warehouses"])
app.include_router(suppliers.router, prefix="/api/suppliers", tags=["suppliers"])
app.include_router(warehouse_products.router, prefix="/api/warehouse-products", tags=["warehouse-products"])
app.include_router(supplier_products.router, prefix="/api/supplier-products", tags=["supplier-products"])
app.include_router(backbone_imports.router, prefix="/api/backbone/import", tags=["backbone-import"])
app.include_router(projections.router, prefix="/api/projections", tags=["projections"])
app.include_router(backbone_reports.router, prefix="/api/backbone/reports", tags=["backbone-reports"])
app.include_router(lanes.router, prefix="/api/lanes", tags=["lanes"])
app.include_router(planning_policies.router, prefix="/api/planning-policies", tags=["planning-policies"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(receipts.router, prefix="/api/receipts", tags=["receipts"])
app.include_router(demand.router, prefix="/api/demand", tags=["demand"])
app.include_router(plan_run.router, prefix="/api/plan", tags=["plan"])
app.include_router(stock_position.router, prefix="/api/stock-position", tags=["stock-position"])
app.include_router(timeline.router, prefix="/api/timeline", tags=["timeline"])
app.include_router(imports_router.router, prefix="/api/import", tags=["imports"])
app.include_router(exports.router, prefix="/api/exports", tags=["exports"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(ingestion.router, prefix="/api/ingestion", tags=["ingestion"])
app.include_router(forecast.router, prefix="/api/forecast", tags=["forecast"])
app.include_router(forecast_v2.router, prefix="/api/v1/forecast", tags=["forecast-v2"])
app.include_router(admin_forecast_methods.router, prefix="/api/admin/forecast-methods", tags=["admin-forecast-methods"])
app.include_router(app_settings.router, prefix="/api/admin/settings", tags=["admin-settings"])
app.include_router(warehouse_product_codes.router, prefix="/api/admin/warehouse-product-codes", tags=["admin-warehouse-product-codes"])
app.include_router(soh_reports.router, prefix="/api/v1/reports/stock-on-hand", tags=["reports-soh"])
app.include_router(sales_reports.router, prefix="/api/v1/reports/sales", tags=["reports-sales"])
app.include_router(data_health.router, prefix="/api/v1/reports/data-health", tags=["reports-data-health"])
app.include_router(stock_coverage_reports.router, prefix="/api/v1/reports/stock-coverage", tags=["reports-stock-coverage"])
app.include_router(diagnostics.router, prefix="/api/v1/diagnostics", tags=["diagnostics"])

# Serve built frontend (after: cd frontend && npm run build)
if _SERVE_FRONTEND:
    app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        """Serve index.html for SPA routes; static files are under /assets."""
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
        file_path = _DIST / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_DIST / "index.html")
else:
    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": "Weekly Supply Planning API", "docs": "/docs"}
