import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.entities import InventoryMovement
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_product, _create_store
from backend.tests.test_skus import _create_sku


async def _setup_inventory_target(
    client: httpx.AsyncClient,
    session: Session,
    *,
    store_external_id: str,
) -> tuple[dict[str, str], dict, dict, dict]:
    create_test_user(
        session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    token = await login(client, "admin", ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}
    store = await _create_store(
        client,
        headers,
        name="库存测试店",
        external_id=store_external_id,
    )
    product = await _create_product(
        client,
        headers,
        store_id=store["id"],
        name="库存测试商品",
    )
    activate_response = await client.patch(
        f"/api/v1/products/{product['id']}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert activate_response.status_code == 200, activate_response.text
    product = activate_response.json()
    sku = await _create_sku(client, headers, product_id=product["id"])
    return headers, store, product, sku


async def _adjust(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    product_id: int,
    sku_id: int,
    movement_type: str,
    change_qty: int,
    expected_version: int,
) -> httpx.Response:
    return await client.post(
        f"/api/v1/products/{product_id}/skus/{sku_id}/inventory/adjustments",
        headers=headers,
        json={
            "movement_type": movement_type,
            "change_qty": change_qty,
            "reason_text": f"测试 {movement_type}",
            "reference_type": "test_case",
            "reference_id": f"{movement_type}-{expected_version}",
            "expected_version": expected_version,
        },
    )


async def test_inventory_adjustment_versioning_movements_and_low_stock(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    headers, store, product, sku = await _setup_inventory_target(
        api_client,
        db_session,
        store_external_id="inventory-store-1",
    )
    detail_url = f"/api/v1/products/{product['id']}/skus/{sku['id']}/inventory"
    detail_response = await api_client.get(detail_url, headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["stock_qty"] == 0
    assert detail_response.json()["version_no"] == 1
    assert detail_response.json()["is_low_stock"] is True

    config_response = await api_client.patch(
        detail_url,
        headers=headers,
        json={"warning_threshold": 5, "location_text": "A-01", "expected_version": 1},
    )
    assert config_response.status_code == 200
    assert config_response.json()["version_no"] == 2

    inbound = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="inbound",
        change_qty=10,
        expected_version=2,
    )
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["inventory"]["stock_qty"] == 10
    assert inbound.json()["inventory"]["version_no"] == 3
    assert inbound.json()["movement"]["before_qty"] == 0
    assert inbound.json()["movement"]["after_qty"] == 10

    lock = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="lock",
        change_qty=4,
        expected_version=3,
    )
    assert lock.status_code == 200
    assert lock.json()["inventory"]["locked_qty"] == 4

    invalid_outbound = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="outbound",
        change_qty=-7,
        expected_version=4,
    )
    assert invalid_outbound.status_code == 409
    assert invalid_outbound.json()["code"] == "LOCKED_STOCK_EXCEEDS_TOTAL"

    unlock = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="unlock",
        change_qty=-2,
        expected_version=4,
    )
    assert unlock.status_code == 200
    outbound = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="outbound",
        change_qty=-7,
        expected_version=5,
    )
    assert outbound.status_code == 200
    final_inventory = outbound.json()["inventory"]
    assert final_inventory["stock_qty"] == 3
    assert final_inventory["locked_qty"] == 2
    assert final_inventory["available_qty"] == 1
    assert final_inventory["is_low_stock"] is True
    assert final_inventory["version_no"] == 6

    stale = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="inbound",
        change_qty=1,
        expected_version=5,
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "INVENTORY_VERSION_CONFLICT"
    assert stale.json()["details"]["current_version"] == 6

    db_session.expire_all()
    movement_count = db_session.scalar(
        select(func.count(InventoryMovement.id)).where(InventoryMovement.sku_id == sku["id"])
    )
    assert movement_count == 4

    movements = await api_client.get(f"{detail_url}/movements?page=1&page_size=10", headers=headers)
    assert movements.status_code == 200
    assert movements.json()["total"] == 4
    assert movements.json()["items"][0]["movement_type"] == "outbound"

    low_stock = await api_client.get(
        f"/api/v1/inventory/low-stock?store_id={store['id']}", headers=headers
    )
    assert low_stock.status_code == 200
    assert low_stock.json()["total"] == 1
    assert low_stock.json()["items"][0]["sku_id"] == sku["id"]


async def test_inventory_validation_permissions_and_product_ownership(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    headers, store, product, sku = await _setup_inventory_target(
        api_client,
        db_session,
        store_external_id="inventory-store-2",
    )
    second_product = await _create_product(
        api_client,
        headers,
        store_id=store["id"],
        name="其他商品",
    )
    invalid_sign = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="outbound",
        change_qty=1,
        expected_version=1,
    )
    assert invalid_sign.status_code == 422

    negative_stock = await _adjust(
        api_client,
        headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="outbound",
        change_qty=-1,
        expected_version=1,
    )
    assert negative_stock.status_code == 409
    assert negative_stock.json()["code"] == "NEGATIVE_INVENTORY_NOT_ALLOWED"

    cross_product = await api_client.get(
        f"/api/v1/products/{second_product['id']}/skus/{sku['id']}/inventory",
        headers=headers,
    )
    assert cross_product.status_code == 404
    assert cross_product.json()["code"] == "SKU_NOT_FOUND"

    create_test_user(
        db_session,
        username="viewer",
        password=VIEWER_PASSWORD,
        role="viewer",
    )
    viewer_token = await login(api_client, "viewer", VIEWER_PASSWORD)
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    readable = await api_client.get("/api/v1/inventory", headers=viewer_headers)
    assert readable.status_code == 200
    forbidden = await _adjust(
        api_client,
        viewer_headers,
        product_id=product["id"],
        sku_id=sku["id"],
        movement_type="inbound",
        change_qty=1,
        expected_version=1,
    )
    assert forbidden.status_code == 403
