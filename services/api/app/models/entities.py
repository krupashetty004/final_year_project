import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(24))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    store_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    pincode: Mapped[str] = mapped_column(String(12), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_min_margin_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    clearance_below_margin_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("mrp_paise > 0", name="ck_products_mrp_pos"),
        CheckConstraint("default_cost_paise >= 0 AND default_cost_paise <= mrp_paise", name="ck_products_cost_le_mrp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    barcode: Mapped[Optional[str]] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str] = mapped_column(String(120), nullable=False)
    variant: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    subcategory: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    unit_type: Mapped[str] = mapped_column(String(16), nullable=False)
    pack_size_value: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    pack_size_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    is_loose_commodity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mrp_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    default_cost_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    gst_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    expiry_category: Mapped[str] = mapped_column(String(32), nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    store_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="SET NULL"))
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_reference: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # PostgreSQL schema already provisions VECTOR(512); null for legacy placeholder rows.
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(512))
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False, default="openai/clip-vit-base-patch32")
    ocr_extracted_text: Mapped[Optional[str]] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    alias_text: Mapped[str] = mapped_column(String(255), nullable=False)
    language_code: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="catalogue")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(24))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    min_order_value_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reliability_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("0.950"))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class StoreInventory(Base):
    __tablename__ = "store_inventory"
    __table_args__ = (
        UniqueConstraint("store_id", "product_id", name="uq_store_inventory_store_product"),
        CheckConstraint("available_qty >= 0", name="ck_inv_available_nonneg"),
        CheckConstraint("reserved_qty >= 0 AND reserved_qty <= available_qty", name="ck_inv_reserved_le_available"),
        CheckConstraint("incoming_qty >= 0", name="ck_inv_incoming_nonneg"),
        CheckConstraint("selling_price_paise > 0", name="ck_inv_price_pos"),
        CheckConstraint("selling_price_paise <= mrp_paise", name="ck_inv_price_le_mrp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    available_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reserved_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    incoming_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    unit_type: Mapped[str] = mapped_column(String(16), nullable=False)
    selling_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    mrp_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    min_margin_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    reorder_point_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    safety_stock_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"))
    supplier_pack_size: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("1"))
    is_listed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    clearance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_price_changed_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class StockBatch(Base):
    __tablename__ = "stock_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_inventory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("store_inventory.id", ondelete="CASCADE"), nullable=False)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    batch_code: Mapped[str] = mapped_column(String(64), nullable=False)
    initial_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    remaining_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    cost_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    manufactured_date: Mapped[Optional[date]] = mapped_column(Date)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    clearance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_batches.id", ondelete="SET NULL"))
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    sold_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_selling_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    total_revenue_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    was_promotional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    festival_tag: Mapped[Optional[str]] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_type: Mapped[str] = mapped_column(String(48), nullable=False)
    store_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class DemandForecast(Base):
    __tablename__ = "demand_forecasts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(48), nullable=False)
    predicted_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    lower_bound_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    upper_bound_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    forecast_error_sigma: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    wape_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    mae_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    rmse_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    mase_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"))
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ReorderSuggestion(Base):
    __tablename__ = "reorder_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"))
    current_available_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    incoming_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    expected_lead_time_demand_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    safety_stock_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reorder_point_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    supplier_pack_size: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    raw_suggested_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    rounded_suggested_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    estimated_cost_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    owner_final_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"))
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    decided_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PricingRecommendation(Base):
    __tablename__ = "pricing_recommendations"
    __table_args__ = (
        CheckConstraint("recommended_price_paise > 0 AND recommended_price_paise <= mrp_paise", name="ck_pr_rec_le_mrp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_batches.id", ondelete="SET NULL"))
    current_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    mrp_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    nearby_median_price_paise: Mapped[Optional[int]] = mapped_column(Integer)
    demand_signal_price_paise: Mapped[Optional[int]] = mapped_column(Integer)
    expiry_discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"))
    competition_signal_price_paise: Mapped[Optional[int]] = mapped_column(Integer)
    stock_pressure_factor: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("1.000"))
    recommended_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_margin_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_sell_through_delta_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    constraints_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    constraint_notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    owner_final_price_paise: Mapped[Optional[int]] = mapped_column(Integer)
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"))
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    decided_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        CheckConstraint("new_price_paise > 0 AND new_price_paise <= mrp_paise", name="ck_ph_price_le_mrp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    old_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    new_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    mrp_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    change_source: Mapped[str] = mapped_column(String(48), nullable=False)
    pricing_recommendation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_recommendations.id", ondelete="SET NULL"))
    changed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    changed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CompetitorPrice(Base):
    __tablename__ = "competitor_prices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    competitor_store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    selling_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InventoryImageUpload(Base):
    __tablename__ = "inventory_image_uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    detector_model: Mapped[str] = mapped_column(String(24), nullable=False, default="rt_detr")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    detected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"))
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DetectedProduct(Base):
    __tablename__ = "detected_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inventory_image_uploads.id", ondelete="CASCADE"), nullable=False)
    bbox_x1: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    bbox_y1: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    bbox_x2: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    bbox_y2: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    detection_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    ocr_text: Mapped[Optional[str]] = mapped_column(Text)
    top_matches_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    selected_product_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"))
    is_unknown: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_action: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    owner_entered_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
    owner_entered_price_paise: Mapped[Optional[int]] = mapped_column(Integer)
    owner_entered_expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    reviewed_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class OwnerApproval(Base):
    __tablename__ = "owner_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    original_value_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    final_value_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    decided_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
