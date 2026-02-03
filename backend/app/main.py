from __future__ import annotations
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Weekly Supply Planning API",
    description="MVP weekly supply planning with SKU/warehouse projections and planned orders",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Weekly Supply Planning API", "docs": "/docs"}
