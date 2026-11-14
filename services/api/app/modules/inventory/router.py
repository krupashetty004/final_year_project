from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.entities import Product, Store, StoreInventory
from app.schemas.common import ProductRead, StoreSummary

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/stores", response_model=list[StoreSummary])
def list_stores(db: Session = Depends(get_db)) -> list[Store]:
    return list(db.scalars(select(Store).order_by(Store.store_code)).all())


@router.get("/products", response_model=list[ProductRead])
def list_products(
    search: str = Query(default="", max_length=120),
    category: str = Query(default="", max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Product]:
    stmt = select(Product)
    if search:
        stmt = stmt.where(Product.name.ilike(f"%{search}%") | Product.brand.ilike(f"%{search}%"))
    if category:
        stmt = stmt.where(Product.category == category)
    stmt = stmt.order_by(Product.sku_code).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/stores/{store_id}/summary")
def get_store_inventory_summary(store_id: str, db: Session = Depends(get_db)) -> dict:
    rows = list(db.scalars(select(StoreInventory).where(StoreInventory.store_id == store_id)).all())
    low_stock = sum(1 for r in rows if r.available_qty > 0 and r.available_qty <= r.reorder_point_qty)
    out_of_stock = sum(1 for r in rows if r.available_qty == 0)
    return {
        "store_id": store_id,
        "total_products": len(rows),
        "low_stock_products": low_stock,
        "out_of_stock_products": out_of_stock,
    }
