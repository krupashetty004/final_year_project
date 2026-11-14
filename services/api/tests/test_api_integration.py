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

    response = client.get(
        f"/api/v1/forecasting/stores/{store_id}/products/{product_id}/backtest"
        "?horizon_days=7&min_train_days=28&step_days=7",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "evaluated"
    assert payload["origin_count"] > 0
    assert set(payload["models"]) == {"moving_average", "seasonal_naive"}
    assert all("wape_pct" in metrics for metrics in payload["models"].values())

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
