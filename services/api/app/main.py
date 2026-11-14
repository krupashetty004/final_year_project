from datetime import datetime, timezone
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import Base, get_db
from app.modules.auth.router import router as auth_router
from app.modules.catalogue.router import router as catalogue_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.forecasting.router import router as forecasting_router
from app.modules.inventory.router import router as inventory_router
from app.modules.pricing.router import router as pricing_router
from app.schemas.common import HealthResponse

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Modular Monolith API for Objectives O1 (Inventory Agent) and O2 (Smart Pricing Agent).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(catalogue_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(forecasting_router, prefix="/api/v1")
app.include_router(pricing_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.get("/health", response_model=HealthResponse, tags=["system"])
@app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    db_ok = False
    table_counts: dict[str, int] = {}
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        for table in Base.metadata.sorted_tables:
            try:
                count = db.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar_one()
                table_counts[table.name] = int(count)
            except Exception:
                table_counts[table.name] = 0
                db_ok = False
    except Exception:
        db_ok = False
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        service="retail-connect-api",
        stage="agent-mvp-beta",
        database_connected=db_ok,
        timestamp_utc=datetime.now(timezone.utc),
        database_engine="postgresql",
        synthetic_seed=settings.SYNTHETIC_SEED,
        gemini_configured=bool(settings.GEMINI_API_KEY),
        table_counts=table_counts,
    )
