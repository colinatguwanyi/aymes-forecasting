# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import (
    products,
    warehouses,
    suppliers,
    lanes,
    planning_policies,
    inventory,
    receipts,
    demand,
    plan_run,
    imports_router,
    exports,
    templates,
)

logger = logging.getLogger(__name__)

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.warning(
        "Database not available at startup (%s). App will run but API will fail until Postgres is running.",
        e,
    )

# Path to built frontend (when running from backend/ or project root)
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
_SERVE_FRONTEND = _DIST.is_dir()

app = FastAPI(
    title="Weekly Supply Planning API",
    description="MVP weekly supply planning with SKU/warehouse projections and planned orders",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(warehouses.router, prefix="/api/warehouses", tags=["warehouses"])
app.include_router(suppliers.router, prefix="/api/suppliers", tags=["suppliers"])
app.include_router(lanes.router, prefix="/api/lanes", tags=["lanes"])
app.include_router(planning_policies.router, prefix="/api/planning-policies", tags=["planning-policies"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(receipts.router, prefix="/api/receipts", tags=["receipts"])
app.include_router(demand.router, prefix="/api/demand", tags=["demand"])
app.include_router(plan_run.router, prefix="/api/plan", tags=["plan"])
app.include_router(imports_router.router, prefix="/api/import", tags=["imports"])
app.include_router(exports.router, prefix="/api/exports", tags=["exports"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])

# Serve built frontend (after: cd frontend && npm run build)
if _SERVE_FRONTEND:
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

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
