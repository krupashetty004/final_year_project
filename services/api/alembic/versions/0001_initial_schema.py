"""Initial schema for AI Powered Retail Connect (18 tables).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-13
"""
from pathlib import Path
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = Path(__file__).resolve().parents[3] / "database" / "migrations" / "0001_initial_schema.sql"
    op.execute(sql_path.read_text(encoding="utf-8"))


def downgrade() -> None:
    for table in [
        "owner_approvals",
        "detected_products",
        "inventory_image_uploads",
        "competitor_prices",
        "price_history",
        "pricing_recommendations",
        "reorder_suggestions",
        "demand_forecasts",
        "agent_runs",
        "sales",
        "stock_batches",
        "store_inventory",
        "suppliers",
        "product_aliases",
        "product_images",
        "products",
        "stores",
        "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
