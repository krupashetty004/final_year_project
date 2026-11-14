from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from math import ceil
import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_current_owner, require_owned_store
from app.database.session import get_db
from app.models.entities import (
    DetectedProduct, InventoryImageUpload, OwnerApproval, PriceHistory, Product, StockBatch,
    StoreInventory, Store, Supplier, User, ProductImage,
)
from app.schemas.common import ProductRead, StoreSummary

router = APIRouter(prefix="/inventory", tags=["inventory"])
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@router.get("/stores", response_model=list[StoreSummary])
def list_stores(
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> list[Store]:
    """Return only stores belonging to the authenticated owner."""
    return list(db.scalars(
        select(Store).where(Store.owner_id == owner.id).order_by(Store.store_code)
    ).all())


@router.get("/products", response_model=list[ProductRead])
def list_products(
    search: str = Query(default="", max_length=120),
    category: str = Query(default="", max_length=80),
    limit: int = Query(default=50, ge=1, le=2000),
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
def get_store_inventory_summary(
    store_id: UUID,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    rows = list(db.scalars(select(StoreInventory).where(StoreInventory.store_id == store_id)).all())
    low_stock = sum(1 for r in rows if r.available_qty > 0 and r.available_qty <= r.reorder_point_qty)
    out_of_stock = sum(1 for r in rows if r.available_qty == 0)
    return {
        "store_id": str(store_id),
        "total_products": len(rows),
        "low_stock_products": low_stock,
        "out_of_stock_products": out_of_stock,
    }




class InventoryUpdateBody(BaseModel):
    available_qty: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    reserved_qty: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    selling_price_paise: int = Field(gt=0)
    version: int = Field(ge=1)


@router.get("/stores/{store_id}/inventory")
def list_store_inventory(
    store_id: UUID,
    search: str = Query(default="", max_length=120),
    filter: str = Query(default="all", pattern="^(all|low_stock|out_of_stock|expiring_soon|loose)$"),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    stmt = (
        select(StoreInventory, Product)
        .join(Product, Product.id == StoreInventory.product_id)
        .where(StoreInventory.store_id == store_id)
    )
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Product.sku_code.ilike(pattern)
            | Product.name.ilike(pattern)
            | Product.brand.ilike(pattern)
        )
    if filter == "low_stock":
        stmt = stmt.where(
            StoreInventory.available_qty > 0,
            StoreInventory.available_qty <= StoreInventory.reorder_point_qty,
        )
    elif filter == "out_of_stock":
        stmt = stmt.where(StoreInventory.available_qty == 0)
    elif filter == "loose":
        stmt = stmt.where(Product.is_loose_commodity.is_(True))
    elif filter == "expiring_soon":
        # Filter after joining the batch rows below to avoid dialect-specific
        # date arithmetic in the stock inventory query.
        pass
    rows = db.execute(stmt.order_by(Product.sku_code)).all()
    items = []
    cutoff = date.today() + timedelta(days=7)
    for inventory, product in rows:
        batch = db.scalar(
            select(StockBatch).where(
                StockBatch.store_id == store_id,
                StockBatch.product_id == product.id,
                StockBatch.remaining_qty > 0,
                StockBatch.expiry_date.is_not(None),
            ).order_by(StockBatch.expiry_date).limit(1)
        )
        nearest_expiry = batch.expiry_date if batch else None
        if filter == "expiring_soon" and not (
            nearest_expiry and date.today() <= nearest_expiry <= cutoff
        ):
            continue
        supplier = db.get(Supplier, inventory.supplier_id) if inventory.supplier_id else None
        items.append({
            "id": str(inventory.id),
            "product_id": str(product.id),
            "sku_code": product.sku_code,
            "name": product.name,
            "brand": product.brand,
            "category": product.category,
            "available_qty": float(inventory.available_qty),
            "reserved_qty": float(inventory.reserved_qty),
            "incoming_qty": float(inventory.incoming_qty),
            "unit_type": inventory.unit_type,
            "selling_price_paise": inventory.selling_price_paise,
            "cost_price_paise": inventory.cost_price_paise,
            "mrp_paise": inventory.mrp_paise,
            "reorder_point_qty": float(inventory.reorder_point_qty),
            "supplier_name": supplier.name if supplier else None,
            "lead_time_days": supplier.lead_time_days if supplier else None,
            "nearest_expiry_date": nearest_expiry.isoformat() if nearest_expiry else None,
            "is_loose_commodity": int(product.is_loose_commodity),
            "clearance_enabled": int(inventory.clearance_enabled),
            "version": inventory.version,
        })
    return {"items": items}


@router.patch("/stores/{store_id}/inventory/{inventory_id}")
def update_store_inventory(
    store_id: UUID,
    inventory_id: UUID,
    body: InventoryUpdateBody,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    store = require_owned_store(str(store_id), owner, db)
    item = db.scalar(select(StoreInventory).where(
        StoreInventory.id == inventory_id,
        StoreInventory.store_id == store_id,
    ).with_for_update())
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if item.version != body.version:
        raise HTTPException(status_code=409, detail="Inventory was changed by another request; refresh and retry")
    if body.reserved_qty > body.available_qty:
        raise HTTPException(status_code=422, detail="Reserved quantity cannot exceed available quantity")
    if body.selling_price_paise > item.mrp_paise:
        raise HTTPException(status_code=422, detail="Selling price cannot exceed MRP")
    margin_floor = (
        ceil(item.cost_price_paise / 100) * 100
        if item.clearance_enabled and store.clearance_below_margin_allowed
        else ceil(item.cost_price_paise * (1 + item.min_margin_bps / 10000) / 100) * 100
    )
    if body.selling_price_paise < margin_floor:
        raise HTTPException(status_code=422, detail="Selling price violates the configured minimum margin")
    old_price = item.selling_price_paise
    item.available_qty = body.available_qty
    item.reserved_qty = body.reserved_qty
    item.selling_price_paise = body.selling_price_paise
    item.version += 1
    if item.selling_price_paise != old_price:
        db.add(PriceHistory(
            store_id=store_id, product_id=item.product_id,
            old_price_paise=old_price, new_price_paise=item.selling_price_paise,
            mrp_paise=item.mrp_paise, change_source="owner_manual",
            changed_by_user_id=owner.id,
        ))
    db.commit()
    return {
        "id": str(item.id), "available_qty": float(item.available_qty),
        "reserved_qty": float(item.reserved_qty),
        "selling_price_paise": item.selling_price_paise, "version": item.version,
    }


@router.get("/stores/{store_id}/batches")
def list_store_batches(
    store_id: UUID,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    rows = db.execute(
        select(StockBatch, Product)
        .join(Product, Product.id == StockBatch.product_id)
        .where(StockBatch.store_id == store_id)
        .order_by(StockBatch.expiry_date.asc().nullslast())
        .limit(500)
    ).all()
    today = date.today()
    batches = []
    for batch, product in rows:
        days_left = (batch.expiry_date - today).days if batch.expiry_date else None
        if days_left is None:
            expiry_category = "no expiry date"
        elif days_left <= 0:
            expiry_category = "expired"
        elif days_left <= 7:
            expiry_category = "expires within 7 days"
        elif days_left <= 14:
            expiry_category = "expires within 14 days"
        else:
            expiry_category = "in date"
        batches.append({
            "id": str(batch.id), "sku_code": product.sku_code,
            "name": product.name, "batch_code": batch.batch_code,
            "remaining_qty": float(batch.remaining_qty),
            "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else "",
            "status": batch.status, "expiry_category": expiry_category,
        })
    return {"batches": batches}


@router.post("/stores/{store_id}/products/{product_id}/reference-images", status_code=201)
async def upload_product_reference_image(
    store_id: UUID,
    product_id: UUID,
    file: UploadFile = File(...),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    """Embed and persist a real owner-uploaded reference photo for one SKU."""
    require_owned_store(str(store_id), owner, db)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Catalogue product not found")
    suffix = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not suffix:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG and WebP images are supported")
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be non-empty and no larger than 10 MB")

    current_references = db.scalars(select(ProductImage.id).where(
        ProductImage.product_id == product_id,
        ProductImage.is_reference.is_(True),
        (ProductImage.store_id.is_(None)) | (ProductImage.store_id == store_id),
    ).limit(25)).all()
    if len(current_references) >= 25:
        raise HTTPException(status_code=409, detail="A maximum of 25 reference images is allowed per SKU and store")

    vision_url = get_settings().VISION_SERVICE_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            response = await client.post(
                f"{vision_url}/embed",
                files={"file": (file.filename or f"{product.sku_code}{suffix}", raw, file.content_type)},
            )
            response.raise_for_status()
        result = response.json()
        embedding = result.get("embedding")
        model_name = result.get("model")
        if (
            not isinstance(embedding, list)
            or len(embedding) != 512
            or not model_name
            or not all(isinstance(value, (int, float)) for value in embedding)
        ):
            raise ValueError("Vision service did not return a valid 512-dimensional embedding")
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not embed reference image: {exc}")

    reference_id = uuid4()
    filename = f"{reference_id}{suffix}"
    reference_dir = (
        Path(__file__).resolve().parents[3]
        / "uploads" / "references" / str(store_id) / str(product_id)
    )
    reference_dir.mkdir(parents=True, exist_ok=True)
    file_path = reference_dir / filename
    relative_path = str(Path("uploads") / "references" / str(store_id) / str(product_id) / filename)
    file_path.write_bytes(raw)
    reference = ProductImage(
        id=reference_id,
        product_id=product_id,
        store_id=store_id,
        image_url=f"local://{relative_path.replace(chr(92), '/')}",
        storage_path=relative_path.replace(chr(92), "/"),
        is_reference=True,
        embedding=embedding,
        embedding_model=model_name,
    )
    try:
        db.add(reference)
        db.commit()
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise
    return {
        "id": str(reference.id),
        "product_id": str(product_id),
        "sku_code": product.sku_code,
        "embedding_model": model_name,
        "embedding_dimension": len(embedding),
        "is_reference": True,
    }


@router.get("/stores/{store_id}/products/{product_id}/reference-images")
def list_product_reference_images(
    store_id: UUID,
    product_id: UUID,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    """List real and placeholder reference-image metadata for the selected SKU."""
    require_owned_store(str(store_id), owner, db)
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Catalogue product not found")
    rows = db.scalars(select(ProductImage).where(
        ProductImage.product_id == product_id,
        ProductImage.is_reference.is_(True),
        (ProductImage.store_id.is_(None)) | (ProductImage.store_id == store_id),
    ).order_by(ProductImage.created_at_utc.desc())).all()
    return {
        "product_id": str(product_id),
        "references": [
            {
                "id": str(row.id),
                "embedding_model": row.embedding_model,
                "embedded": row.embedding is not None,
                "source": "store_upload" if row.store_id == store_id else "seeded_or_global",
                "created_at_utc": row.created_at_utc.isoformat(),
                "ocr_extracted_text": row.ocr_extracted_text,
            }
            for row in rows
        ],
    }


@router.post("/stores/{store_id}/images/analyze")
async def analyze_inventory_photo(
    store_id: UUID,
    file: UploadFile = File(...),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    """Persist a shelf photo, run vision/OCR matching, and queue owner review."""
    require_owned_store(str(store_id), owner, db)
    suffix = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not suffix:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG and WebP images are supported")
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be non-empty and no larger than 10 MB")

    upload_id = uuid4()
    filename = f"{upload_id}{suffix}"
    upload_dir = Path(__file__).resolve().parents[3] / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / filename
    file_path.write_bytes(raw)
    relative_path = f"uploads/{filename}"

    upload = InventoryImageUpload(
        id=upload_id, store_id=store_id, uploaded_by_user_id=owner.id,
        image_url=f"local://{relative_path}", storage_path=relative_path,
        detector_model="yolo11", status="processing",
    )
    db.add(upload)
    db.commit()

    products = list(db.scalars(select(Product).order_by(Product.sku_code).limit(2000)).all())
    reference_rows = db.scalars(select(ProductImage).where(
        ProductImage.is_reference.is_(True),
        ProductImage.embedding.is_not(None),
        or_(ProductImage.store_id.is_(None), ProductImage.store_id == store_id),
    )).all()
    references_by_product: dict[UUID, list[list[float]]] = {}
    for reference in reference_rows:
        if reference.embedding is not None:
            references_by_product.setdefault(reference.product_id, []).append(
                [float(value) for value in reference.embedding]
            )
    catalogue = [{
        "product_id": str(p.id), "sku_code": p.sku_code, "barcode": p.barcode or "",
        "name": p.name, "brand": p.brand, "variant": p.variant,
        "reference_embeddings": references_by_product.get(p.id, []),
    } for p in products]
    vision_url = get_settings().VISION_SERVICE_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            response = await client.post(
                f"{vision_url}/analyze",
                files={"file": (filename, raw, file.content_type)},
                data={"catalogue_json": json.dumps(catalogue)},
            )
            response.raise_for_status()
        result = response.json()
        saved_detections = []
        for detection in result.get("detections", []):
            bbox = detection.get("bbox", [0, 0, 0, 0])
            record = DetectedProduct(
                upload_id=upload_id,
                bbox_x1=Decimal(str(bbox[0])), bbox_y1=Decimal(str(bbox[1])),
                bbox_x2=Decimal(str(bbox[2])), bbox_y2=Decimal(str(bbox[3])),
                detection_confidence=Decimal(str(detection.get("detection_confidence", 0))),
                ocr_text=detection.get("ocr_text") or None,
                top_matches_json=detection.get("top_matches", []),
                is_unknown=bool(detection.get("is_unknown", True)),
                owner_action="pending",
            )
            db.add(record)
            saved_detections.append(record)
        db.flush()
        for detection, record in zip(result.get("detections", []), saved_detections):
            detection["detected_product_id"] = str(record.id)
        upload.detected_count = len(saved_detections)
        upload.status = "ready_for_review"
        db.commit()
        return {
            "upload_id": str(upload_id),
            "status": upload.status,
            "detected_count": upload.detected_count,
            "vision": result,
            "owner_action_required": "Select/correct each SKU and enter the quantity physically counted.",
        }
    except (httpx.HTTPError, ValueError) as exc:
        upload.status = "failed"
        db.commit()
        raise HTTPException(status_code=502, detail=f"Vision analysis failed; photo retained for retry: {exc}")





@router.get("/stores/{store_id}/images")
def list_inventory_photo_reviews(
    store_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    """List persisted shelf-photo uploads and their owner-review state."""
    require_owned_store(str(store_id), owner, db)
    uploads = db.scalars(
        select(InventoryImageUpload)
        .where(InventoryImageUpload.store_id == store_id)
        .order_by(InventoryImageUpload.created_at_utc.desc())
        .limit(limit)
    ).all()
    upload_ids = [upload.id for upload in uploads]
    detections_by_upload: dict[UUID, list[DetectedProduct]] = {upload_id: [] for upload_id in upload_ids}
    if upload_ids:
        detections = db.scalars(
            select(DetectedProduct)
            .where(DetectedProduct.upload_id.in_(upload_ids))
            .order_by(DetectedProduct.created_at_utc.asc())
        ).all()
        for detection in detections:
            detections_by_upload.setdefault(detection.upload_id, []).append(detection)

    return {
        "uploads": [
            {
                "id": str(upload.id),
                "status": upload.status,
                "detector_model": upload.detector_model,
                "detected_count": upload.detected_count,
                "created_at_utc": upload.created_at_utc.isoformat(),
                "detections": [
                    {
                        "id": str(detection.id),
                        "bbox": [
                            float(detection.bbox_x1), float(detection.bbox_y1),
                            float(detection.bbox_x2), float(detection.bbox_y2),
                        ],
                        "detection_confidence": float(detection.detection_confidence),
                        "ocr_text": detection.ocr_text or "",
                        "top_matches": detection.top_matches_json or [],
                        "is_unknown": detection.is_unknown,
                        "owner_action": detection.owner_action,
                        "selected_product_id": (
                            str(detection.selected_product_id) if detection.selected_product_id else None
                        ),
                        "owner_entered_qty": (
                            str(detection.owner_entered_qty) if detection.owner_entered_qty is not None else None
                        ),
                    }
                    for detection in detections_by_upload.get(upload.id, [])
                ],
            }
            for upload in uploads
        ]
    }


class RejectDetectionBody(BaseModel):
    notes: str | None = Field(default=None, max_length=500)


@router.post("/stores/{store_id}/images/{upload_id}/detections/{detection_id}/reject")
def reject_inventory_detection(
    store_id: UUID,
    upload_id: UUID,
    detection_id: UUID,
    body: RejectDetectionBody,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    upload = db.scalar(select(InventoryImageUpload).where(
        InventoryImageUpload.id == upload_id,
        InventoryImageUpload.store_id == store_id,
    ))
    detection = db.scalar(select(DetectedProduct).where(
        DetectedProduct.id == detection_id,
        DetectedProduct.upload_id == upload_id,
    ).with_for_update())
    if not upload or not detection:
        raise HTTPException(status_code=404, detail="Photo upload or detection not found")
    if detection.owner_action != "pending":
        raise HTTPException(status_code=409, detail="This detection has already been reviewed")
    now = datetime.now(timezone.utc)
    detection.owner_action = "rejected"
    detection.reviewed_at_utc = now
    db.add(OwnerApproval(
        store_id=store_id, user_id=owner.id,
        entity_type="detected_product", entity_id=detection.id,
        decision="rejected",
        original_value_json={"top_matches": detection.top_matches_json or []},
        final_value_json={"rejected": True},
        notes=body.notes,
    ))
    pending = db.scalar(select(DetectedProduct.id).where(
        DetectedProduct.upload_id == upload_id,
        DetectedProduct.owner_action == "pending",
        DetectedProduct.id != detection.id,
    ).limit(1))
    if not pending:
        upload.status = "confirmed"
    db.commit()
    return {
        "upload_id": str(upload_id),
        "detection_id": str(detection.id),
        "owner_action": detection.owner_action,
        "upload_status": upload.status,
        "inventory_changed": False,
    }


class ConfirmDetectionBody(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    selling_price_paise: int | None = Field(default=None, gt=0)
    expiry_date: date | None = None
    notes: str | None = Field(default=None, max_length=500)


@router.post("/stores/{store_id}/images/{upload_id}/detections/{detection_id}/confirm")
def confirm_inventory_detection(
    store_id: UUID,
    upload_id: UUID,
    detection_id: UUID,
    body: ConfirmDetectionBody,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    """Apply owner-confirmed quantity as a stock addition; never infer counts."""
    store = require_owned_store(str(store_id), owner, db)
    upload = db.scalar(select(InventoryImageUpload).where(
        InventoryImageUpload.id == upload_id,
        InventoryImageUpload.store_id == store_id,
    ))
    detection = db.scalar(select(DetectedProduct).where(
        DetectedProduct.id == detection_id, DetectedProduct.upload_id == upload_id,
    ).with_for_update())
    if not upload or not detection:
        raise HTTPException(status_code=404, detail="Photo upload or detection not found")
    if detection.owner_action != "pending":
        raise HTTPException(status_code=409, detail="This detection has already been reviewed")
    if body.expiry_date and body.expiry_date < date.today():
        raise HTTPException(status_code=422, detail="Expired stock cannot be added to available inventory")
    product = db.get(Product, body.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Selected SKU not found")
    item = db.scalar(select(StoreInventory).where(
        StoreInventory.store_id == store_id,
        StoreInventory.product_id == body.product_id,
    ).with_for_update())
    old_qty = Decimal("0")
    if item:
        old_qty = Decimal(item.available_qty)
        new_qty = old_qty + body.quantity
        if new_qty < Decimal(item.reserved_qty):
            raise HTTPException(status_code=422, detail="New available stock cannot be below reserved quantity")
        item.available_qty = new_qty
        if body.selling_price_paise is not None:
            if body.selling_price_paise > item.mrp_paise:
                raise HTTPException(status_code=422, detail="Selling price cannot exceed MRP")
            margin_floor = (
                ceil(item.cost_price_paise / 100) * 100
                if item.clearance_enabled and store.clearance_below_margin_allowed
                else ceil(item.cost_price_paise * (1 + item.min_margin_bps / 10000) / 100) * 100
            )
            if body.selling_price_paise < margin_floor:
                raise HTTPException(status_code=422, detail="Selling price violates the store's minimum margin")
            item.selling_price_paise = body.selling_price_paise
        item.version += 1
    else:
        price = body.selling_price_paise or product.mrp_paise
        if price > product.mrp_paise:
            raise HTTPException(status_code=422, detail="Selling price cannot exceed MRP")
        minimum_price = ceil(product.default_cost_paise * 1.10 / 100) * 100
        if price < minimum_price:
            raise HTTPException(status_code=422, detail="Selling price violates the default 10% minimum margin")
        item = StoreInventory(
            store_id=store_id, product_id=product.id, available_qty=body.quantity,
            reserved_qty=Decimal("0"), incoming_qty=Decimal("0"),
            unit_type=product.unit_type, selling_price_paise=price,
            cost_price_paise=product.default_cost_paise, mrp_paise=product.mrp_paise,
            min_margin_bps=1000, reorder_point_qty=Decimal("0"),
            safety_stock_qty=Decimal("0"), supplier_pack_size=Decimal("1"),
            is_listed=True, clearance_enabled=False, version=1,
        )
        db.add(item)
    db.flush()
    if body.expiry_date:
        if body.expiry_date <= date.today():
            raise HTTPException(status_code=422, detail="Expiry date must be in the future")
        status_value = "expiring_soon" if body.expiry_date <= date.today() + timedelta(days=7) else "active"
        db.add(StockBatch(
            store_inventory_id=item.id, store_id=store_id, product_id=product.id,
            batch_code=f"PHOTO-{uuid4().hex[:12].upper()}",
            initial_qty=body.quantity, remaining_qty=body.quantity,
            cost_price_paise=item.cost_price_paise, expiry_date=body.expiry_date,
            status=status_value,
        ))
    detection.selected_product_id = product.id
    top_match_id = (detection.top_matches_json or [{}])[0].get("product_id")
    detection.owner_action = "confirmed" if top_match_id == str(product.id) else "corrected"
    detection.owner_entered_qty = body.quantity
    detection.owner_entered_price_paise = body.selling_price_paise
    detection.owner_entered_expiry_date = body.expiry_date
    detection.reviewed_at_utc = datetime.now(timezone.utc)
    db.add(OwnerApproval(
        store_id=store_id, user_id=owner.id, entity_type="detected_product",
        entity_id=detection.id,
        decision="confirmed" if detection.owner_action == "confirmed" else "edited",
        original_value_json={"top_matches": detection.top_matches_json or []},
        final_value_json={
            "product_id": str(product.id), "sku_code": product.sku_code,
            "quantity_added": str(body.quantity),
            "expiry_date": body.expiry_date.isoformat() if body.expiry_date else None,
        },
        notes=body.notes,
    ))
    pending = db.scalar(select(DetectedProduct.id).where(
        DetectedProduct.upload_id == upload_id,
        DetectedProduct.owner_action == "pending",
        DetectedProduct.id != detection.id,
    ).limit(1))
    if not pending:
        upload.status = "confirmed"
    db.commit()
    return {
        "upload_id": str(upload_id), "detection_id": str(detection.id),
        "product_id": str(product.id), "sku_code": product.sku_code,
        "quantity_added": str(body.quantity), "previous_available_qty": str(old_qty),
        "new_available_qty": str(item.available_qty), "owner_action": detection.owner_action,
        "upload_status": upload.status,
    }
