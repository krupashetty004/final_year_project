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
