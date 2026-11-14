"""Enable row-level security on Retail Connect application tables.

Revision ID: 0002_enable_retail_rls
Revises: 0001_initial_schema
Create Date: 2026-11-14
"""
from pathlib import Path
from alembic import op

revision = "0002_enable_retail_rls"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    filename = Path("database/migrations/0002_enable_retail_rls.sql")
    candidates = [Path.cwd() / filename]
    candidates.extend(parent / filename for parent in Path(__file__).resolve().parents)
    sql_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if sql_path is None:
        raise FileNotFoundError(
            "Could not locate database/migrations/0002_enable_retail_rls.sql."
        )
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
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
