from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_owner, require_owned_store
from app.database.session import get_db
from app.models.entities import (
    CompetitorPrice, OwnerApproval, PriceHistory, PricingRecommendation,
    StockBatch, Store, StoreInventory, User,
)
from app.modules.pricing.engine import PricingInputs, recommend_price

router = APIRouter(prefix="/pricing", tags=["pricing"])


class ApprovalBody(BaseModel):
    decision: str = Field(pattern="^(accepted|edited|rejected)$")
    final_price_paise: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)


@router.get("/status")
def pricing_module_status() -> dict:
    return {
        "module": "smart_pricing",
        "stage": "rule_based_recommendations_with_owner_approval",
        "signals": ["verified competitor median", "near-expiry markdown", "excess-stock pressure"],
        "not_yet_enabled": ["learned price elasticity", "validated demand-response model", "sell-through uplift calibration"],
        "guardrails": [
            "selling_price <= mrp", "minimum margin except explicitly enabled clearance",
            "maximum +/-10% price movement", "one approved change per SKU per day",
            "whole-rupee rounding", "no personalized pricing", "owner approval required",
        ],
    }


@router.post("/stores/{store_id}/recommendations/generate")
def generate_pricing_recommendations(
    store_id: UUID,
    product_id: UUID | None = None,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    store = require_owned_store(str(store_id), owner, db)
    stmt = select(StoreInventory).where(StoreInventory.store_id == store_id)
    if product_id:
        stmt = stmt.where(StoreInventory.product_id == product_id)
    items = list(db.scalars(stmt).all())
    now = datetime.now(timezone.utc)
    generated = []
    skipped = 0
    for item in items:
        pending_id = db.scalar(select(PricingRecommendation.id).where(
            PricingRecommendation.store_id == store_id,
            PricingRecommendation.product_id == item.product_id,
            PricingRecommendation.status == "pending",
        ).limit(1))
        if pending_id:
            skipped += 1
            continue
        peer_rows = db.scalars(
            select(CompetitorPrice.selling_price_paise).where(
                CompetitorPrice.product_id == item.product_id,
                CompetitorPrice.is_verified.is_(True),
                CompetitorPrice.observed_at_utc >= now - timedelta(days=30),
                CompetitorPrice.distance_km <= 2,
            )
        ).all()
        peer_prices = sorted(int(v) for v in peer_rows)
        median = None
        if peer_prices:
            mid = len(peer_prices) // 2
            median = peer_prices[mid] if len(peer_prices) % 2 else (peer_prices[mid - 1] + peer_prices[mid]) // 2
        batch = db.scalar(
            select(StockBatch).where(
                StockBatch.store_id == store_id, StockBatch.product_id == item.product_id,
                StockBatch.remaining_qty > 0, StockBatch.expiry_date.is_not(None),
            ).order_by(StockBatch.expiry_date).limit(1)
        )
        days_expiry = (batch.expiry_date - now.date()).days if batch else None
        # Only excess inventory creates stock-pressure markdown. A low-stock
        # condition must never be treated as overstock.
        stock_pressure = 1.0
        if item.reorder_point_qty and item.available_qty > item.reorder_point_qty * Decimal('1.5'):
            stock_pressure = min(3.0, float(item.available_qty / item.reorder_point_qty))
        try:
            result = recommend_price(PricingInputs(
                current_price_paise=item.selling_price_paise,
                mrp_paise=item.mrp_paise,
                cost_price_paise=item.cost_price_paise,
                min_margin_bps=item.min_margin_bps,
                nearby_median_price_paise=median,
                days_to_expiry=days_expiry,
                stock_pressure_factor=stock_pressure,
                clearance_allowed=bool(item.clearance_enabled and store.clearance_below_margin_allowed),
            ))
        except ValueError:
            skipped += 1
            continue
        rec = PricingRecommendation(
            store_id=item.store_id, product_id=item.product_id,
            batch_id=batch.id if batch else None,
            current_price_paise=item.selling_price_paise, mrp_paise=item.mrp_paise,
            cost_price_paise=item.cost_price_paise, nearby_median_price_paise=median,
            expiry_discount_pct=result["expiry_discount_pct"],
            competition_signal_price_paise=median,
            stock_pressure_factor=stock_pressure,
            recommended_price_paise=result["recommended_price_paise"],
            expected_margin_bps=result["expected_margin_bps"],
            explanation=result["explanation"], constraints_passed=result["constraints_passed"],
            status="pending",
        )
        db.add(rec)
        generated.append(rec)
    db.commit()
    return {
        "store_id": str(store_id), "created_count": len(generated), "skipped_count": skipped,
        "recommendations": [
            {"id": str(r.id), "product_id": str(r.product_id),
             "current_price_paise": r.current_price_paise,
             "recommended_price_paise": r.recommended_price_paise, "status": r.status}
            for r in generated
        ],
    }


@router.get("/stores/{store_id}/recommendations")
def list_recommendations(
    store_id: UUID,
    status: str = Query(default="pending", pattern="^(pending|accepted|edited|rejected|expired|all)$"),
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    stmt = select(PricingRecommendation).where(PricingRecommendation.store_id == store_id)
    if status != "all":
        stmt = stmt.where(PricingRecommendation.status == status)
    rows = db.scalars(stmt.order_by(PricingRecommendation.created_at_utc.desc()).limit(200)).all()
    return {"recommendations": [
        {"id": str(r.id), "product_id": str(r.product_id),
         "current_price_paise": r.current_price_paise,
         "recommended_price_paise": r.recommended_price_paise,
         "status": r.status, "explanation": r.explanation}
        for r in rows
    ]}


@router.post("/stores/{store_id}/recommendations/{recommendation_id}/decision")
def decide_recommendation(
    store_id: UUID,
    recommendation_id: UUID,
    body: ApprovalBody,
    owner: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> dict:
    require_owned_store(str(store_id), owner, db)
    rec = db.scalar(select(PricingRecommendation).where(
        PricingRecommendation.id == recommendation_id,
        PricingRecommendation.store_id == store_id,
    ).with_for_update())
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.status != "pending":
        raise HTTPException(status_code=409, detail="Recommendation has already been decided")
    item = db.scalar(select(StoreInventory).where(
        StoreInventory.store_id == store_id,
        StoreInventory.product_id == rec.product_id,
    ).with_for_update())
    store = db.get(Store, store_id)
    if not item or not store:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if item.selling_price_paise != rec.current_price_paise:
        raise HTTPException(status_code=409, detail="Current price changed after this recommendation was generated")
    now = datetime.now(timezone.utc)
    original = {"price_paise": item.selling_price_paise}
    if body.decision == "rejected":
        rec.status = "rejected"
        rec.decided_at_utc = now
        db.add(OwnerApproval(
            store_id=store_id, user_id=owner.id,
            entity_type="pricing_recommendation", entity_id=rec.id,
            decision="rejected", original_value_json=original,
            final_value_json=original, notes=body.notes,
        ))
        db.commit()
        return {"id": str(rec.id), "status": rec.status}
    final_price = body.final_price_paise if body.decision == "edited" else rec.recommended_price_paise
    if final_price is None:
        raise HTTPException(status_code=422, detail="final_price_paise is required when editing")
    if final_price % 100 != 0:
        raise HTTPException(status_code=422, detail="Prices must be rounded to whole rupees")
    if final_price > rec.mrp_paise:
        raise HTTPException(status_code=422, detail="Approved price cannot exceed MRP")
    min_price = (
        item.cost_price_paise
        if item.clearance_enabled and store.clearance_below_margin_allowed
        else ceil(item.cost_price_paise * (1 + item.min_margin_bps / 10000))
    )
    if final_price < min_price:
        raise HTTPException(status_code=422, detail="Approved price violates minimum margin")
    lower = ceil(item.selling_price_paise * 0.90 / 100) * 100
    upper = int(item.selling_price_paise * 1.10 // 100) * 100
    if not lower <= final_price <= upper:
        raise HTTPException(status_code=422, detail="Approved price exceeds the 10% daily movement guardrail")
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if item.last_price_changed_at_utc and item.last_price_changed_at_utc >= today_start:
        raise HTTPException(status_code=409, detail="A price change has already been approved today")
    old_price = item.selling_price_paise
    item.selling_price_paise = final_price
    item.last_price_changed_at_utc = now
    item.version += 1
    rec.owner_final_price_paise = final_price
    rec.status = "accepted" if body.decision == "accepted" else "edited"
    rec.decided_at_utc = now
    db.add(OwnerApproval(
        store_id=store_id, user_id=owner.id,
        entity_type="pricing_recommendation", entity_id=rec.id,
        decision=rec.status, original_value_json={"price_paise": old_price},
        final_value_json={"price_paise": final_price}, notes=body.notes,
    ))
    if final_price != old_price:
        db.add(PriceHistory(
            store_id=store_id, product_id=rec.product_id,
            old_price_paise=old_price, new_price_paise=final_price,
            mrp_paise=rec.mrp_paise,
            change_source="pricing_agent_approved" if body.decision == "accepted" else "pricing_agent_edited",
            pricing_recommendation_id=rec.id, changed_by_user_id=owner.id,
        ))
    db.commit()
    return {"id": str(rec.id), "status": rec.status, "final_price_paise": final_price}
