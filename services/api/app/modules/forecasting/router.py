from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_owner, require_owned_store
from app.database.session import get_db
from app.models.entities import OwnerApproval, Product, ReorderSuggestion, Sale, StoreInventory, Supplier, User
from app.modules.forecasting.engine import calculate_reorder, forecast_demand, rolling_origin_backtest

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


def _daily_series(rows: list[tuple], days: int = 180) -> list[float]:
    """Build a complete daily series, retaining zero-sale days."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    totals: dict[date, float] = {}
    for row in rows:
        sold_at, quantity = row[0], row[1]
        day = sold_at.date()
        totals[day] = totals.get(day, 0.0) + float(quantity)
    return [totals.get(start + timedelta(days=i), 0.0) for i in range(days)]


@router.get("/status")
def forecasting_module_status() -> dict:
    return {
        "module": "forecasting",
        "stage": "baseline_forecasting_with_rolling_origin_evaluation",
        "models": ["moving_average", "seasonal_naive"],
        "evaluation": ["expanding_window_rolling_origin", "MAE", "WAPE", "bias"],
        "not_yet_enabled": ["Croston-TSB", "LightGBM", "N-HiTS", "production model selection"],
    }




@router.get("/stores/{store_id}/sales-history")
def get_sales_history(
    store_id: UUID,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    since = datetime.now(timezone.utc) - timedelta(days=180)
    rows = db.execute(
        select(Sale.sold_at_utc, Sale.quantity, Sale.total_revenue_paise, Sale.festival_tag).where(
            Sale.store_id == store_id, Sale.sold_at_utc >= since,
        ).order_by(Sale.sold_at_utc)
    ).all()
    daily: dict[date, dict] = {}
    for sold_at, quantity, revenue, festival in rows:
        day = sold_at.date()
        entry = daily.setdefault(day, {"date": day.isoformat(), "units_sold": 0.0,
                                       "revenue_paise": 0, "festival_tag": None})
        entry["units_sold"] += float(quantity)
        entry["revenue_paise"] += int(revenue)
        if festival:
            entry["festival_tag"] = festival
    series = [daily[day] for day in sorted(daily)]
    return {"store_id": str(store_id), "days": len(series), "series": series}


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
        select(Sale.sold_at_utc, Sale.quantity, Sale.is_synthetic).where(
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
        "data_quality": "synthetic_history_included" if any(bool(row[2]) for row in rows) else "historical_sales",
    }


@router.get("/stores/{store_id}/products/{product_id}/backtest")
def get_forecast_backtest(
    store_id: UUID,
    product_id: UUID,
    horizon_days: int = Query(default=7, ge=1, le=30),
    min_train_days: int = Query(default=28, ge=7, le=120),
    step_days: int = Query(default=7, ge=1, le=30),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    """Evaluate both deterministic demand baselines on historical rolling origins."""
    require_owned_store(str(store_id), owner, db)
    exists = db.scalar(select(StoreInventory.id).where(
        StoreInventory.store_id == store_id,
        StoreInventory.product_id == product_id,
    ))
    if not exists:
        raise HTTPException(status_code=404, detail="Inventory item not found for this store")

    since = datetime.now(timezone.utc) - timedelta(days=180)
    rows = db.execute(
        select(Sale.sold_at_utc, Sale.quantity, Sale.is_synthetic).where(
            Sale.store_id == store_id,
            Sale.product_id == product_id,
            Sale.sold_at_utc >= since,
        ).order_by(Sale.sold_at_utc)
    ).all()
    daily = _daily_series(rows)
    if not rows or not any(daily):
        raise HTTPException(status_code=422, detail="No sales history available for backtesting")

    result = rolling_origin_backtest(
        daily,
        horizon_days=horizon_days,
        min_train_days=min_train_days,
        step_days=step_days,
    )
    return {
        "store_id": str(store_id),
        "product_id": str(product_id),
        "history_days": len(daily),
        "data_quality": (
            "synthetic_history_included" if any(bool(row[2]) for row in rows)
            else "historical_sales"
        ),
        **result,
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



class ReorderDecisionBody(BaseModel):
    decision: str = Field(pattern="^(accepted|edited|rejected)$")
    final_qty: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)


@router.get("/stores/{store_id}/reorder-suggestions")
def list_reorder_suggestions(
    store_id: UUID,
    status: str = Query(default="pending", pattern="^(pending|accepted|edited|rejected|all)$"),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    stmt = select(ReorderSuggestion).where(ReorderSuggestion.store_id == store_id)
    if status != "all":
        stmt = stmt.where(ReorderSuggestion.status == status)
    rows = db.scalars(stmt.order_by(ReorderSuggestion.created_at_utc.desc()).limit(200)).all()
    return {"suggestions": [
        {
            "id": str(row.id), "product_id": str(row.product_id),
            "sku_code": (db.get(Product, row.product_id).sku_code if db.get(Product, row.product_id) else ""),
            "product_name": (db.get(Product, row.product_id).name if db.get(Product, row.product_id) else ""),
            "current_available_qty": float(row.current_available_qty),
            "suggested_qty": float(row.rounded_suggested_qty),
            "supplier_pack_size": float(row.supplier_pack_size),
            "estimated_cost_paise": row.estimated_cost_paise,
            "explanation": row.explanation, "status": row.status,
        }
        for row in rows
    ]}


@router.post("/stores/{store_id}/reorder-suggestions/{suggestion_id}/decision")
def decide_reorder_suggestion(
    store_id: UUID,
    suggestion_id: UUID,
    body: ReorderDecisionBody,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    row = db.scalar(select(ReorderSuggestion).where(
        ReorderSuggestion.id == suggestion_id,
        ReorderSuggestion.store_id == store_id,
    ).with_for_update())
    if not row:
        raise HTTPException(status_code=404, detail="Reorder suggestion not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Suggestion has already been decided")
    original = {"suggested_qty": str(row.rounded_suggested_qty)}
    final_qty = None
    decision = body.decision
    if decision == "rejected":
        row.status = "rejected"
    else:
        final_qty = float(body.final_qty if decision == "edited" else row.rounded_suggested_qty)
        pack = float(row.supplier_pack_size)
        if abs((final_qty / pack) - round(final_qty / pack)) > 1e-8:
            raise HTTPException(status_code=422, detail="Final quantity must be a multiple of supplier pack size")
        row.owner_final_qty = final_qty
        row.status = "accepted" if decision == "accepted" else "edited"
    now = datetime.now(timezone.utc)
    row.decided_at_utc = now
    db.add(OwnerApproval(
        store_id=store_id, user_id=owner.id,
        entity_type="reorder_suggestion", entity_id=row.id,
        decision=row.status, original_value_json=original,
        final_value_json={"final_qty": str(final_qty)} if final_qty is not None else {},
        notes=body.notes,
    ))
    db.commit()
    return {"id": str(row.id), "status": row.status, "owner_final_qty": final_qty,
            "purchase_order_created": False}
