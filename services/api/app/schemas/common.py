import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    stage: str
    database_connected: bool
    timestamp_utc: datetime
    database_engine: str = "postgresql"
    synthetic_seed: int = 42
    gemini_configured: bool = False
    table_counts: dict[str, int] = Field(default_factory=dict)


class StoreSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    store_code: str
    name: str
    address: str
    city: str
    state: str
    pincode: str
    latitude: float
    longitude: float
    is_verified: bool
    default_min_margin_bps: int
    clearance_below_margin_allowed: bool
    is_synthetic: bool


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku_code: str
    barcode: Optional[str] = None
    name: str
    brand: str
    variant: str
    category: str
    unit_type: str
    pack_size_value: Decimal
    pack_size_unit: str
    is_loose_commodity: bool
    mrp_paise: int = Field(..., gt=0)
    default_cost_paise: int = Field(..., ge=0)
    expiry_category: str
    is_synthetic: bool
