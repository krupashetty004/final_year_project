import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RETAIL_CONNECT_INTEGRATION") != "1",
    reason="Set RETAIL_CONNECT_INTEGRATION=1 after applying PostgreSQL migrations and seed import",
)


@pytest.fixture(scope="module")
def owner_client():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "ramesh@lakshmikirana.in",
                "password": "KiranaDemo@2026",
            },
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        yield client, {"Authorization": f"Bearer {token}"}


def test_demo_owner_can_list_only_owned_stores(owner_client):
    client, headers = owner_client
    response = client.get("/api/v1/stores", headers=headers)
    assert response.status_code == 200, response.text
    stores = response.json()["stores"]
    assert stores
    assert all(store["id"] for store in stores)


def test_demo_owner_can_read_inventory_dashboard(owner_client):
    client, headers = owner_client
    stores = client.get("/api/v1/stores", headers=headers).json()["stores"]
    store_id = stores[0]["id"]

    dashboard = client.get(f"/api/v1/stores/{store_id}/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["store"]["id"] == store_id

    inventory = client.get(
        f"/api/v1/inventory/stores/{store_id}/inventory",
        headers=headers,
    )
    assert inventory.status_code == 200, inventory.text
    assert isinstance(inventory.json()["items"], list)


def test_demo_owner_can_read_catalogue_and_sales_history(owner_client):
    client, headers = owner_client
    catalogue = client.get("/api/v1/products?limit=5", headers=headers)
    assert catalogue.status_code == 200, catalogue.text
    assert isinstance(catalogue.json()["items"], list)
    assert catalogue.json()["total"] > 0

    stores = client.get("/api/v1/stores", headers=headers).json()["stores"]
    store_id = stores[0]["id"]
    history = client.get(
        f"/api/v1/forecasting/stores/{store_id}/sales-history",
        headers=headers,
    )
    assert history.status_code == 200, history.text
    assert isinstance(history.json()["series"], list)



def test_inventory_store_metadata_requires_owner_and_is_tenant_scoped(owner_client):
    client, headers = owner_client
    store_id = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]

    assert client.get("/api/v1/inventory/stores").status_code == 401
    assert client.get(f"/api/v1/inventory/stores/{store_id}/summary").status_code == 401

    stores = client.get("/api/v1/inventory/stores", headers=headers)
    assert stores.status_code == 200, stores.text
    assert all(row["id"] == store_id for row in stores.json())

    summary = client.get(
        f"/api/v1/inventory/stores/{store_id}/summary",
        headers=headers,
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["store_id"] == store_id


def test_owner_can_list_persisted_shelf_photo_reviews(owner_client):
    client, headers = owner_client
    store_id = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    response = client.get(
        f"/api/v1/inventory/stores/{store_id}/images",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["uploads"], list)


def test_owner_can_list_product_reference_image_status(owner_client):
    client, headers = owner_client
    store_id = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    product = client.get("/api/v1/products?limit=1", headers=headers).json()["items"][0]
    response = client.get(
        f"/api/v1/inventory/stores/{store_id}/products/{product['id']}/reference-images",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["references"], list)
    assert all("embedded" in item for item in response.json()["references"])


def test_owner_reference_upload_stores_512d_embedding(owner_client, monkeypatch):
    client, headers = owner_client
    store_id = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    product = client.get("/api/v1/products?limit=1", headers=headers).json()["items"][0]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "embedding": [1.0] + [0.0] * 511,
                "dimension": 512,
                "model": "openai/clip-vit-base-patch32",
                "normalization": "l2",
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "app.modules.inventory.router.httpx.AsyncClient",
        FakeAsyncClient,
    )
    response = client.post(
        f"/api/v1/inventory/stores/{store_id}/products/{product['id']}/reference-images",
        headers=headers,
        files={"file": ("package.png", b"test image bytes", "image/png")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["embedding_dimension"] == 512

    listed = client.get(
        f"/api/v1/inventory/stores/{store_id}/products/{product['id']}/reference-images",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == response.json()["id"] and item["embedded"] for item in listed.json()["references"])

    from uuid import UUID

    from app.database.session import SessionLocal
    from app.modules.inventory.router import _match_product_reference_vectors

    with SessionLocal() as db:
        matches = _match_product_reference_vectors(
            db,
            UUID(store_id),
            [1.0] + [0.0] * 511,
        )
    assert matches
    assert matches[0]["product_id"] == product["id"]
    assert matches[0]["score_type"] == "cosine_similarity"


def test_owner_can_run_sku_rolling_origin_backtest(owner_client):
    from uuid import UUID

    from sqlalchemy import select

    from app.database.session import SessionLocal
    from app.models.entities import Sale

    client, headers = owner_client
    store_id = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    with SessionLocal() as db:
        product_id = db.scalar(
            select(Sale.product_id)
            .where(Sale.store_id == UUID(store_id))
            .distinct()
            .limit(1)
        )
    assert product_id is not None

    endpoint = (
        f"/api/v1/forecasting/stores/{store_id}/products/{product_id}/backtest"
        "?horizon_days=7&min_train_days=28&step_days=7"
    )
    real_only = client.get(endpoint, headers=headers)
    assert real_only.status_code == 422, real_only.text
    assert "No real sales history" in real_only.json()["detail"]

    response = client.get(
        endpoint + "&include_synthetic=true",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "evaluated"
    assert payload["origin_count"] > 0
    assert payload["include_synthetic"] is True
    assert payload["data_quality"] == "synthetic_history_included"
    assert set(payload["models"]) == {"moving_average", "seasonal_naive", "croston_tsb"}
    assert all("wape_pct" in metrics for metrics in payload["models"].values())



def test_owner_can_auto_select_reorder_forecast_baseline(owner_client):
    client, headers = owner_client
    store_id = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    response = client.post(
        f"/api/v1/forecasting/stores/{store_id}/reorder-suggestions/generate?model=auto",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["forecast_model"] == "auto"
    assert payload["model_selection_method"] == (
        "lowest_wape_rolling_origin_with_moving_average_fallback"
    )
    assert set(payload["models_used"]).issubset({
        "moving_average", "seasonal_naive", "croston_tsb",
    })



def test_owner_can_generate_reorders_with_croston_tsb(owner_client):
    client, headers = owner_client
    store_id = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    response = client.post(
        f"/api/v1/forecasting/stores/{store_id}/reorder-suggestions/generate?model=croston_tsb",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["forecast_model"] == "croston_tsb"


def test_pricing_comparison_filters_demo_and_old_peer_rows(owner_client):
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy import select

    from app.database.session import SessionLocal
    from app.models.entities import CompetitorPrice, Store, StoreInventory

    client, headers = owner_client
    store_id_text = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    store_id = UUID(store_id_text)
    with SessionLocal() as db:
        product_id = db.scalar(
            select(StoreInventory.product_id).where(StoreInventory.store_id == store_id).limit(1)
        )
        peers = db.scalars(
            select(Store).where(Store.id != store_id, Store.is_verified.is_(True))
            .order_by(Store.store_code).limit(2)
        ).all()
        assert product_id is not None and len(peers) == 2
        now = datetime.now(timezone.utc)
        db.add_all([
            CompetitorPrice(
                product_id=product_id, competitor_store_id=peers[0].id,
                observed_at_utc=now - timedelta(days=5), selling_price_paise=10000,
                distance_km=Decimal("1"), is_verified=True, is_synthetic=False,
            ),
            CompetitorPrice(
                product_id=product_id, competitor_store_id=peers[0].id,
                observed_at_utc=now - timedelta(days=2), selling_price_paise=11000,
                distance_km=Decimal("1"), is_verified=True, is_synthetic=False,
            ),
            CompetitorPrice(
                product_id=product_id, competitor_store_id=peers[1].id,
                observed_at_utc=now - timedelta(days=1), selling_price_paise=12000,
                distance_km=Decimal("1.5"), is_verified=True, is_synthetic=False,
            ),
            CompetitorPrice(
                product_id=product_id, competitor_store_id=peers[1].id,
                observed_at_utc=now, selling_price_paise=1000,
                distance_km=Decimal("1"), is_verified=True, is_synthetic=True,
            ),
            CompetitorPrice(
                product_id=product_id, competitor_store_id=peers[0].id,
                observed_at_utc=now, selling_price_paise=500,
                distance_km=Decimal("3"), is_verified=True, is_synthetic=False,
            ),
        ])
        db.commit()

    response = client.get(
        f"/api/v1/pricing/stores/{store_id_text}/competitor-comparison",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    row = next(item for item in response.json()["comparisons"] if item["product_id"] == str(product_id))
    assert row["nearby_verified_stores"] == 2
    assert row["nearby_median_paise"] == 11500


def test_pricing_recommendation_uses_only_real_sales_demand_trend(owner_client):
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy import select

    from app.database.session import SessionLocal
    from app.models.entities import PricingRecommendation, Sale, StoreInventory

    client, headers = owner_client
    store_id_text = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    store_id = UUID(store_id_text)
    with SessionLocal() as db:
        inventory = db.scalar(
            select(StoreInventory).where(StoreInventory.store_id == store_id).limit(1)
        )
        assert inventory is not None
        now = datetime.now(timezone.utc)
        rows = []
        # Prior 28 days: one unit per day.
        for day_offset in range(8, 36):
            qty = Decimal("1.000")
            rows.append(Sale(
                store_id=store_id, product_id=inventory.product_id,
                sold_at_utc=now - timedelta(days=day_offset),
                quantity=qty, unit_type=inventory.unit_type,
                unit_selling_price_paise=inventory.selling_price_paise,
                unit_cost_paise=inventory.cost_price_paise,
                total_revenue_paise=int(qty * inventory.selling_price_paise),
                is_synthetic=False,
            ))
        # Recent 7 days: two units per day, a 2x baseline trend.
        for day_offset in range(0, 7):
            qty = Decimal("2.000")
            rows.append(Sale(
                store_id=store_id, product_id=inventory.product_id,
                sold_at_utc=now - timedelta(days=day_offset),
                quantity=qty, unit_type=inventory.unit_type,
                unit_selling_price_paise=inventory.selling_price_paise,
                unit_cost_paise=inventory.cost_price_paise,
                total_revenue_paise=int(qty * inventory.selling_price_paise),
                is_synthetic=False,
            ))
        db.add_all(rows)
        db.commit()
        product_id = inventory.product_id

    response = client.post(
        f"/api/v1/pricing/stores/{store_id_text}/recommendations/generate"
        f"?product_id={product_id}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created_count"] == 1

    with SessionLocal() as db:
        recommendation = db.scalar(select(PricingRecommendation).where(
            PricingRecommendation.store_id == store_id,
            PricingRecommendation.product_id == product_id,
            PricingRecommendation.status == "pending",
        ).order_by(PricingRecommendation.created_at_utc.desc()).limit(1))
        assert recommendation is not None
        assert recommendation.demand_signal_price_paise is not None
        assert recommendation.demand_signal_price_paise > recommendation.current_price_paise
        assert "+3% demand-trend signal was considered" in recommendation.explanation


def test_manual_inventory_price_edit_obeys_daily_price_change_guard(owner_client):
    from datetime import datetime, timezone
    from uuid import UUID

    from sqlalchemy import select

    from app.database.session import SessionLocal
    from app.models.entities import StoreInventory

    client, headers = owner_client
    store_id_text = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    store_id = UUID(store_id_text)
    with SessionLocal() as db:
        item = db.scalar(
            select(StoreInventory).where(StoreInventory.store_id == store_id).limit(1)
        )
        assert item is not None
        inventory_id = item.id
        original = {
            "mrp": item.mrp_paise,
            "cost": item.cost_price_paise,
            "margin": item.min_margin_bps,
            "last_changed": item.last_price_changed_at_utc,
        }
        current = item.selling_price_paise
        item.mrp_paise = current + 10000
        item.cost_price_paise = max(0, current // 2)
        item.min_margin_bps = 1000
        item.last_price_changed_at_utc = datetime.now(timezone.utc)
        version = item.version
        db.commit()

    response = client.patch(
        f"/api/v1/inventory/stores/{store_id_text}/inventory/{inventory_id}",
        headers=headers,
        json={
            "available_qty": 10,
            "reserved_qty": 0,
            "selling_price_paise": current + 100,
            "version": version,
        },
    )
    assert response.status_code == 409, response.text

    with SessionLocal() as db:
        item = db.get(StoreInventory, inventory_id)
        item.mrp_paise = original["mrp"]
        item.cost_price_paise = original["cost"]
        item.min_margin_bps = original["margin"]
        item.last_price_changed_at_utc = original["last_changed"]
        db.commit()


def test_pricing_approval_obeys_same_india_local_daily_guard(owner_client):
    from datetime import datetime, timezone
    from uuid import UUID

    from sqlalchemy import select

    from app.database.session import SessionLocal
    from app.models.entities import PricingRecommendation, StoreInventory

    client, headers = owner_client
    store_id_text = client.get("/api/v1/stores", headers=headers).json()["stores"][0]["id"]
    store_id = UUID(store_id_text)
    with SessionLocal() as db:
        item = db.scalar(
            select(StoreInventory).where(StoreInventory.store_id == store_id).limit(1)
        )
        assert item is not None
        original = {
            "mrp": item.mrp_paise,
            "cost": item.cost_price_paise,
            "margin": item.min_margin_bps,
            "last_changed": item.last_price_changed_at_utc,
        }
        current = item.selling_price_paise
        item.mrp_paise = current + 10000
        item.cost_price_paise = max(0, current // 2)
        item.min_margin_bps = 1000
        item.last_price_changed_at_utc = datetime.now(timezone.utc)
        recommendation = PricingRecommendation(
            store_id=store_id,
            product_id=item.product_id,
            current_price_paise=current,
            mrp_paise=item.mrp_paise,
            cost_price_paise=item.cost_price_paise,
            recommended_price_paise=current + 100,
            expected_margin_bps=5000,
            explanation="Integration test recommendation",
            constraints_passed=True,
            status="pending",
        )
        db.add(recommendation)
        db.flush()
        recommendation_id = recommendation.id
        db.commit()

    response = client.post(
        f"/api/v1/pricing/stores/{store_id_text}/recommendations/{recommendation_id}/decision",
        headers=headers,
        json={"decision": "accepted"},
    )
    assert response.status_code == 409, response.text

    with SessionLocal() as db:
        item = db.scalar(select(StoreInventory).where(StoreInventory.store_id == store_id))
        item.mrp_paise = original["mrp"]
        item.cost_price_paise = original["cost"]
        item.min_margin_bps = original["margin"]
        item.last_price_changed_at_utc = original["last_changed"]
        recommendation = db.get(PricingRecommendation, recommendation_id)
        if recommendation:
            db.delete(recommendation)
        db.commit()

def test_store_data_cannot_be_read_by_another_owner(owner_client):
    client, headers = owner_client
    stores = client.get("/api/v1/stores", headers=headers).json()["stores"]
    store_id = stores[0]["id"]
    # A valid but unrelated UUID must not expose another tenant's data.
    response = client.get(
        "/api/v1/stores/00000000-0000-0000-0000-000000000001/dashboard",
        headers=headers,
    )
    assert response.status_code == 404
