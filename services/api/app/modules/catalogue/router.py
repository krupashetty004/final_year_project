from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.entities import Product
from app.schemas.common import ProductRead

router = APIRouter(prefix="/products", tags=["product catalogue"])


class ProductCreateBody(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    brand: str = Field(min_length=1, max_length=120)
    variant: str = Field(default="", max_length=120)
    category: str = Field(min_length=1, max_length=80)
    subcategory: str = Field(default="", max_length=80)
    unit_type: str = Field(pattern="^(pcs|kg|g|l|ml|pack)$")
    pack_size_value: float = Field(gt=0, le=100000)
    pack_size_unit: str = Field(min_length=1, max_length=16)
    is_loose_commodity: bool = False
    mrp_paise: int = Field(gt=0)
    default_cost_paise: int = Field(ge=0)
    expiry_category: str = Field(pattern="^(dairy|bakery|snacks|grocery|other)$")
    barcode: str | None = Field(default=None, max_length=64)


@router.get("", response_model=dict)
def list_catalogue(
    search: str = Query(default="", max_length=120),
    category: str = Query(default="", max_length=80),
    loose_only: bool = False,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Product)
    count_stmt = select(func.count(Product.id))
    if search:
        pattern = f"%{search}%"
        condition = (
            Product.name.ilike(pattern)
            | Product.brand.ilike(pattern)
            | Product.sku_code.ilike(pattern)
            | Product.barcode.ilike(pattern)
        )
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    if category:
        stmt = stmt.where(Product.category == category)
        count_stmt = count_stmt.where(Product.category == category)
    if loose_only:
        stmt = stmt.where(Product.is_loose_commodity.is_(True))
        count_stmt = count_stmt.where(Product.is_loose_commodity.is_(True))
    total = int(db.scalar(count_stmt) or 0)
    categories = db.execute(
        select(Product.category, func.count(Product.id))
        .group_by(Product.category)
        .order_by(Product.category)
    ).all()
    products = db.scalars(stmt.order_by(Product.sku_code).offset(offset).limit(limit)).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "categories": [{"category": name, "count": count} for name, count in categories],
        "items": [ProductRead.model_validate(product).model_dump(mode="json") for product in products],
    }


@router.post("", response_model=ProductRead, status_code=201)
def create_catalogue_product(
    body: ProductCreateBody,
    db: Session = Depends(get_db),
) -> Product:
    if body.default_cost_paise > body.mrp_paise:
        raise HTTPException(status_code=422, detail="Default cost cannot exceed MRP")
    if body.barcode and db.scalar(select(Product.id).where(Product.barcode == body.barcode)):
        raise HTTPException(status_code=409, detail="A product with this barcode already exists")
    product = Product(
        sku_code=f"RC-{uuid4().hex[:12].upper()}",
        barcode=body.barcode,
        name=body.name.strip(),
        brand=body.brand.strip(),
        variant=body.variant.strip(),
        category=body.category.strip(),
        subcategory=body.subcategory.strip(),
        unit_type=body.unit_type,
        pack_size_value=body.pack_size_value,
        pack_size_unit=body.pack_size_unit,
        is_loose_commodity=body.is_loose_commodity,
        mrp_paise=body.mrp_paise,
        default_cost_paise=body.default_cost_paise,
        expiry_category=body.expiry_category,
        is_synthetic=False,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
