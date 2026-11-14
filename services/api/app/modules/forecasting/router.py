from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_owner, require_owned_store
from app.database.session import get_db
from app.models.entities import Product, ReorderSuggestion, Sale, StoreInventory, Supplier, User
from app.modules.forecasting.engine import calculate_reorder, forecast_demand

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


def _daily_series(rows: list[tuple], days: int = 180) -> list[float]:
    """Build a complete daily series, retaining zero-sale days."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    totals: dict[date, float] = {}
    for sold_at, quantity in rows:
        day = sold_at.date()
        totals[day] = totals.get(day, 0.0) + float(quantity)
    return [totals.get(start + timedelta(days=i), 0.0) for i in range(days)]


@router.get("/status")
def forecasting_module_status() -> dict:
    return {
        "module": "forecasting",
        "stage": "deterministic_baselines_available",
        "models": ["moving_average", "seasonal_naive"],
        "not_yet_enabled": ["Croston-TSB", "LightGBM", "N-HiTS", "rolling-origin model selection"],
    }


@router.get("/stores/{store_id}/products/{product_id}/forecast")
def get_forecast(
    store_id: UUID,
    product_id: UUID,
    horizon_days: int = Query(default=7, ge=1, le=90),
    model: str = Query(default="moving_average", pattern="^(moving_average|seasonal_naive)$"),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    exists = db.scalar(select(StoreInventory.id).where(
        StoreInventory.store_id == store_id, StoreInventory.product_id == product_id
    ))
    if not exists:
        raise HTTPException(status_code=404, detail="Inventory item not found for this store")
    since = datetime.now(timezone.utc) - timedelta(days=180)
    rows = db.execute(
        select(Sale.sold_at_utc, Sale.quantity).where(
            Sale.store_id == store_id, Sale.product_id == product_id,
            Sale.sold_at_utc >= since,
        ).order_by(Sale.sold_at_utc)
    ).all()
    series = _daily_series(rows)
    if not any(series):
        raise HTTPException(status_code=422, detail="No sales history available for forecasting")
    result = forecast_demand(series, horizon_days=horizon_days, model=model)
    return {
        "store_id": str(store_id), "product_id": str(product_id),
        **result.__dict__, "history_days": len(series),
        "data_quality": "synthetic_history_included" if any(
            getattr(row, "is_synthetic", False) for row in rows
        ) else "historical_sales",
    }


@router.post("/stores/{store_id}/reorder-suggestions/generate")
def generate_reorder_suggestions(
    store_id: UUID,
    horizon_days: int = Query(default=7, ge=1, le=30),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    items = list(db.scalars(select(StoreInventory).where(StoreInventory.store_id == store_id)).all())
    if not items:
        raise HTTPException(status_code=404, detail="No inventory found for store")
    since = datetime.now(timezone.utc) - timedelta(days=180)
    created = []
    skipped_no_history = 0
    skipped_existing_pending = 0
    for item in items:
        existing = db.scalar(select(ReorderSuggestion.id).where(
            ReorderSuggestion.store_id == store_id,
            ReorderSuggestion.product_id == item.product_id,
            ReorderSuggestion.status == "pending",
        ).limit(1))
        if existing:
            skipped_existing_pending += 1
            continue
        rows = db.execute(
            select(Sale.sold_at_utc, Sale.quantity).where(
                Sale.store_id == store_id, Sale.product_id == item.product_id,
                Sale.sold_at_utc >= since,
            ).order_by(Sale.sold_at_utc)
        ).all()
        daily = _daily_series(rows)
        if not any(daily):
            skipped_no_history += 1
            continue
        forecast = forecast_demand(daily, horizon_days=horizon_days, model="moving_average")
        supplier = db.get(Supplier, item.supplier_id) if item.supplier_id else None
        lead_time = supplier.lead_time_days if supplier else 3
        calc = calculate_reorder(
            forecast.daily_mean, forecast.daily_sigma, lead_time,
            float(item.available_qty), float(item.incoming_qty),
            float(item.supplier_pack_size),
        )
        if calc["rounded_suggested_qty"] <= 0:
            continue
        product = db.get(Product, item.product_id)
        suggestion = ReorderSuggestion(
            store_id=item.store_id, product_id=item.product_id,
            supplier_id=item.supplier_id, current_available_qty=item.available_qty,
            incoming_qty=item.incoming_qty,
            expected_lead_time_demand_qty=calc["expected_lead_time_demand_qty"],
            safety_stock_qty=calc["safety_stock_qty"],
            reorder_point_qty=calc["reorder_point_qty"],
            supplier_pack_size=item.supplier_pack_size,
            raw_suggested_qty=calc["raw_suggested_qty"],
            rounded_suggested_qty=calc["rounded_suggested_qty"],
            estimated_cost_paise=int(round(calc["rounded_suggested_qty"] * item.cost_price_paise)),
            explanation=(
                f"{product.sku_code}: 180-day daily moving-average baseline; "
                "lead-time demand + 1.65 sigma safety stock; supplier-pack rounding. "
                "This is a recommendation only; owner approval is required."
            ),
            status="pending",
        )
        db.add(suggestion)
        created.append(suggestion)
    db.commit()
    return {
        "store_id": str(store_id), "created_count": len(created),
        "skipped_no_history": skipped_no_history,
        "skipped_existing_pending": skipped_existing_pending,
        "suggestions": [
            {"id": str(s.id), "product_id": str(s.product_id),
             "qty": float(s.rounded_suggested_qty), "status": s.status}
            for s in created
        ],
    }
