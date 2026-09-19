import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.entities import InventoryItem, InventoryMovement
from backend.tests.test_auth_and_users import VIEWER_PASSWORD, create_test_user, login
from backend.tests.test_inventory import _adjust, _setup_inventory_target
from backend.tests.test_products import _create_store


async def test_inventory_advice_is_explainable_persisted_and_read_only(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    headers, store, product, sku = await _setup_inventory_target(
        api_client,
        db_session,
        store_external_id="advice-store-1",
    )
    inventory_url = f"/api/v1/products/{product['id']}/skus/{sku['id']}/inventory"
    config = await api_client.patch(
        inventory_url,
        headers=headers,
        json={"warning_threshold": 5, "expected_version": 1},
    )
    assert config.status_code == 200
    inbound = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="inbound",
        change_qty=20,
        expected_version=2,
    )
    assert inbound.status_code == 200
    first_outbound = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="outbound",
        change_qty=-5,
        expected_version=3,
    )
    assert first_outbound.status_code == 200
    second_outbound = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="outbound",
        change_qty=-12,
        expected_version=4,
    )
    assert second_outbound.status_code == 200
    before = second_outbound.json()["inventory"]

    generate = await api_client.post(
        f"/api/v1/stores/{store['id']}/inventory-advice/generate",
        headers=headers,
        json={},
    )
    assert generate.status_code == 200, generate.text
    run = generate.json()
    assert run["rule_version"] == "inventory-rule-v1"
    assert run["item_count"] == 1
    assert run["replenish_count"] == 1
    assert run["insufficient_count"] == 0
    item = run["items"][0]
    assert item["sku_id"] == sku["id"]
    assert item["outbound_qty"] == 17
    assert item["outbound_events"] == 2
    assert item["available_qty"] == 3
    assert item["target_stock_qty"] == 10
    assert item["suggested_restock_qty"] == 7
    assert item["action"] == "replenish"
    assert item["data_status"] == "sufficient"
    assert "建议补货 7 件" in item["explanation"]

    after_response = await api_client.get(inventory_url, headers=headers)
    assert after_response.status_code == 200
    after = after_response.json()
    assert after["stock_qty"] == before["stock_qty"]
    assert after["locked_qty"] == before["locked_qty"]
    assert after["version_no"] == before["version_no"]

    db_session.expire_all()
    movement_count = db_session.scalar(
        select(func.count(InventoryMovement.id)).where(InventoryMovement.sku_id == sku["id"])
    )
    assert movement_count == 3

    latest = await api_client.get(f"/api/v1/stores/{store['id']}/inventory-advice", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["id"] == run["id"]
    history = await api_client.get(
        f"/api/v1/stores/{store['id']}/inventory-advice/runs", headers=headers
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1

    other_store = await _create_store(
        api_client,
        headers,
        name="其他建议店铺",
        external_id="advice-store-other",
    )
    cross_store = await api_client.get(
        f"/api/v1/stores/{other_store['id']}/inventory-advice/runs/{run['id']}",
        headers=headers,
    )
    assert cross_store.status_code == 404
    assert cross_store.json()["code"] == "INVENTORY_ADVICE_NOT_FOUND"


async def test_inventory_advice_reports_insufficient_data_and_enforces_permissions(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    headers, store, product, sku = await _setup_inventory_target(
        api_client,
        db_session,
        store_external_id="advice-store-2",
    )
    before_inventory = db_session.scalar(
        select(InventoryItem).where(InventoryItem.sku_id == sku["id"])
    )
    assert before_inventory is not None
    before_version = before_inventory.version_no

    generate = await api_client.post(
        f"/api/v1/stores/{store['id']}/inventory-advice/generate",
        headers=headers,
        json={"lookback_days": 30, "min_outbound_events": 2},
    )
    assert generate.status_code == 200
    run = generate.json()
    assert run["insufficient_count"] == 1
    assert "数据不足" in run["message"]
    assert run["items"][0]["action"] == "monitor"
    assert run["items"][0]["data_status"] == "insufficient"

    db_session.expire_all()
    after_inventory = db_session.scalar(
        select(InventoryItem).where(InventoryItem.sku_id == sku["id"])
    )
    assert after_inventory is not None
    assert after_inventory.version_no == before_version

    create_test_user(
        db_session,
        username="viewer",
        password=VIEWER_PASSWORD,
        role="viewer",
    )
    viewer_token = await login(api_client, "viewer", VIEWER_PASSWORD)
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    readable = await api_client.get(
        f"/api/v1/stores/{store['id']}/inventory-advice", headers=viewer_headers
    )
    assert readable.status_code == 200
    forbidden = await api_client.post(
        f"/api/v1/stores/{store['id']}/inventory-advice/generate",
        headers=viewer_headers,
        json={},
    )
    assert forbidden.status_code == 403

    deactivate = await api_client.patch(
        f"/api/v1/stores/{store['id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert deactivate.status_code == 200
    inactive = await api_client.post(
        f"/api/v1/stores/{store['id']}/inventory-advice/generate",
        headers=headers,
        json={},
    )
    assert inactive.status_code == 409
    assert inactive.json()["code"] == "STORE_INACTIVE"
