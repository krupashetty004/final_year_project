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
    filename = Path("database/migrations/0001_initial_schema.sql")
    candidates = [Path.cwd() / filename]
    candidates.extend(parent / filename for parent in Path(__file__).resolve().parents)
    sql_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if sql_path is None:
        raise FileNotFoundError(
            "Could not locate database/migrations/0001_initial_schema.sql. "
            "Run Alembic from the API directory with the repository database folder mounted."
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
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
