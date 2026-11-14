"""Stage 1 foundation constraint tests (money in paise, price <= MRP, reserved <= available)."""
from decimal import Decimal
import uuid

from app.models.entities import Product, StoreInventory


def test_store_inventory_model_fields() -> None:
    inv = StoreInventory(
        id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        available_qty=Decimal("25.000"),
        reserved_qty=Decimal("5.000"),
        incoming_qty=Decimal("12.000"),
        unit_type="pcs",
        selling_price_paise=4800,
        cost_price_paise=4000,
        mrp_paise=5000,
        min_margin_bps=1000,
        version=1,
    )
    assert inv.selling_price_paise <= inv.mrp_paise
    assert inv.reserved_qty <= inv.available_qty
    assert isinstance(inv.selling_price_paise, int)


def test_loose_product_unit_support() -> None:
    prod = Product(
        id=uuid.uuid4(),
        sku_code="SKU-TEST-001",
        name="Sona Masoori Rice (Loose per kg)",
        brand="Kirana Loose",
        variant="Classic",
        category="Rice and grains",
        subcategory="Sona Masoori Rice",
        unit_type="kg",
        pack_size_value=Decimal("1.000"),
        pack_size_unit="kg",
        is_loose_commodity=True,
        mrp_paise=7200,
        default_cost_paise=5800,
        expiry_category="grocery",
        is_synthetic=True,
    )
    assert prod.is_loose_commodity is True
    assert prod.unit_type == "kg"
