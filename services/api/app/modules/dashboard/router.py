from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_owner, require_owned_store
from app.database.session import get_db
from app.models.entities import Product, Sale, StockBatch, Store, StoreInventory, User

router = APIRouter(tags=["store dashboard"])




@router.get("/stores")
def list_owner_stores(
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    """Return only stores owned by the authenticated user."""
    stores = db.scalars(
        select(Store).where(Store.owner_id == owner.id).order_by(Store.store_code)
    ).all()
    return {"stores": [
        {
            "id": str(store.id),
            "store_code": store.store_code,
            "name": store.name,
            "address": store.address,
            "city": store.city,
            "state": store.state,
            "pincode": store.pincode,
            "latitude": store.latitude,
            "longitude": store.longitude,
            "is_verified": store.is_verified,
            "default_min_margin_bps": store.default_min_margin_bps,
            "clearance_below_margin_allowed": store.clearance_below_margin_allowed,
            "is_synthetic": store.is_synthetic,
        }
        for store in stores
    ]}


@router.get("/stores/{store_id}/dashboard")
def get_store_dashboard(
    store_id: UUID,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    store = require_owned_store(str(store_id), owner, db)
    inventory_rows = db.execute(
        select(StoreInventory, Product)
        .join(Product, Product.id == StoreInventory.product_id)
        .where(StoreInventory.store_id == store_id)
    ).all()
    total_products = len(inventory_rows)
    total_available = sum(float(inv.available_qty) for inv, _ in inventory_rows)
    low_stock = sum(
        1 for inv, _ in inventory_rows
        if inv.available_qty > 0 and inv.available_qty <= inv.reorder_point_qty
    )
    out_of_stock = sum(1 for inv, _ in inventory_rows if inv.available_qty == 0)
    reorder_required = sum(
        1 for inv, _ in inventory_rows
        if inv.available_qty + inv.incoming_qty < inv.reorder_point_qty
    )
    retail_value = sum(
        int(round(float(inv.available_qty) * inv.selling_price_paise))
        for inv, _ in inventory_rows
    )
    cost_value = sum(
        int(round(float(inv.available_qty) * inv.cost_price_paise))
        for inv, _ in inventory_rows
    )

    today = datetime.now(timezone.utc).date()
    expiring_batches = db.scalars(
        select(StockBatch.id).where(
            StockBatch.store_id == store_id,
            StockBatch.remaining_qty > 0,
            StockBatch.expiry_date >= today,
            StockBatch.expiry_date <= today + timedelta(days=7),
        )
    ).all()

    recent = sorted(inventory_rows, key=lambda pair: pair[0].updated_at_utc or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:10]
    recent_updates = [
        {
            "id": str(inv.id), "sku_code": product.sku_code, "name": product.name,
            "brand": product.brand, "category": product.category,
            "available_qty": float(inv.available_qty), "unit_type": inv.unit_type,
            "selling_price_paise": inv.selling_price_paise, "mrp_paise": inv.mrp_paise,
            "updated_at_utc": inv.updated_at_utc.isoformat() if inv.updated_at_utc else "",
        }
        for inv, product in recent
    ]

    since_30d = datetime.now(timezone.utc) - timedelta(days=30)
    sales = db.execute(
        select(Sale.sold_at_utc, Sale.quantity, Sale.total_revenue_paise, Sale.festival_tag)
        .where(Sale.store_id == store_id, Sale.sold_at_utc >= since_30d)
        .order_by(Sale.sold_at_utc)
    ).all()
    daily: dict[str, dict] = {}
    for sold_at, quantity, revenue, festival in sales:
        day = sold_at.date().isoformat()
        entry = daily.setdefault(day, {
            "day": day, "total_units": 0.0, "revenue_paise": 0, "festival_tag": None,
        })
        entry["total_units"] += float(quantity)
        entry["revenue_paise"] += int(revenue)
        if festival:
            entry["festival_tag"] = festival
    sales_series = [daily[key] for key in sorted(daily)]

    category_totals: dict[str, dict] = {}
    for inv, product in inventory_rows:
        entry = category_totals.setdefault(product.category, {
            "category": product.category, "sku_count": 0,
            "total_qty": 0.0, "retail_value_paise": 0,
        })
        entry["sku_count"] += 1
        entry["total_qty"] += float(inv.available_qty)
        entry["retail_value_paise"] += int(round(float(inv.available_qty) * inv.selling_price_paise))

    return {
        "store": {
            "id": str(store.id), "store_code": store.store_code,
            "name": store.name, "city": store.city, "state": store.state,
            "pincode": store.pincode, "is_verified": int(store.is_verified),
            "default_min_margin_bps": store.default_min_margin_bps,
        },
        "kpis": {
            "total_products": total_products,
            "total_available_units": round(total_available, 3),
            "low_stock_products": low_stock,
            "out_of_stock_products": out_of_stock,
            "reorder_required_products": reorder_required,
            "expiring_products": len(expiring_batches),
            "stock_retail_value_paise": retail_value,
            "stock_cost_value_paise": cost_value,
        },
        "recent_updates": recent_updates,
        "sales_series_30d": sales_series,
        "category_breakdown": list(category_totals.values()),
    }


@router.post("/ai/explain-summary")
def explain_store_summary(
    payload: dict,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    store_id = payload.get("store_id")
    if not store_id:
        raise HTTPException(status_code=422, detail="store_id is required")
    store = require_owned_store(str(store_id), owner, db)
    rows = list(db.scalars(select(StoreInventory).where(StoreInventory.store_id == store.id)).all())
    low_stock = sum(1 for row in rows if row.available_qty > 0 and row.available_qty <= row.reorder_point_qty)
    out_of_stock = sum(1 for row in rows if row.available_qty == 0)
    expiring = db.scalar(
        select(StockBatch.id).where(
            StockBatch.store_id == store.id,
            StockBatch.remaining_qty > 0,
            StockBatch.expiry_date >= datetime.now(timezone.utc).date(),
            StockBatch.expiry_date <= datetime.now(timezone.utc).date() + timedelta(days=7),
        ).limit(1)
    )
    summary = (
        f"{store.name} currently tracks {len(rows)} inventory SKUs. "
        f"{low_stock} are at or below reorder point and {out_of_stock} are out of stock. "
        f"{'At least one stock batch' if expiring else 'No stock batch'} is due to expire within seven days. "
        "Figures are calculated from the store database; this is a deterministic summary."
    )
    return {"summary": summary, "provider": "deterministic-fallback", "fallback_used": True}
