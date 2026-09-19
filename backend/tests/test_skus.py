import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.entities import InventoryItem, InventoryMovement, ProductSku
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_product, _create_store


async def _create_sku(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    product_id: int,
    sku_code: str = "SKU-BLACK-L",
    status: str = "active",
) -> dict:
    response = await client.post(
        f"/api/v1/products/{product_id}/skus",
        headers=headers,
        json={
            "sku_code": sku_code,
            "sku_name": "黑色大号",
            "specs": {"颜色": "黑色", "尺寸": "L"},
            "price": "109.90",
            "cost": "49.50",
            "status": status,
            "platform_sku_id": "TMALL-SKU-BLACK-L",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_sku_create_list_update_and_unique_code(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    token = await login(api_client, "admin", ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}
    store = await _create_store(
        api_client,
        headers,
        name="SKU 测试店",
        external_id="sku-store-1",
    )
    product = await _create_product(api_client, headers, store_id=store["id"], name="SKU 测试商品")
    sku = await _create_sku(api_client, headers, product_id=product["id"])
    assert sku["specs"] == {"颜色": "黑色", "尺寸": "L"}
    assert sku["price"] == "109.90"

    duplicate = await api_client.post(
        f"/api/v1/products/{product['id']}/skus",
        headers=headers,
        json={
            "sku_code": "sku-black-l",
            "sku_name": "重复编码",
            "price": "109.90",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "SKU_CODE_EXISTS"

    invalid_specs = await api_client.post(
        f"/api/v1/products/{product['id']}/skus",
        headers=headers,
        json={
            "sku_code": "SKU-BAD-SPEC",
            "sku_name": "错误规格",
            "specs": {"颜色": {"name": "黑色"}},
            "price": "1.00",
        },
    )
    assert invalid_specs.status_code == 422

    invalid_precision = await api_client.post(
        f"/api/v1/products/{product['id']}/skus",
        headers=headers,
        json={
            "sku_code": "SKU-BAD-PRICE",
            "sku_name": "错误价格",
            "price": "1.001",
        },
    )
    assert invalid_precision.status_code == 422

    list_response = await api_client.get(
        f"/api/v1/products/{product['id']}/skus?status=active&q=BLACK",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    update_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/skus/{sku['id']}",
        headers=headers,
        json={
            "sku_name": "曜石黑大号",
            "specs": {"颜色": "曜石黑", "尺寸": "L"},
            "cost": None,
            "platform_sku_id": None,
        },
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["sku_name"] == "曜石黑大号"
    assert update_response.json()["cost"] is None
    assert update_response.json()["platform_sku_id"] is None


async def test_sku_cross_product_access_and_inventory_history_are_preserved(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin = create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    token = await login(api_client, "admin", ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}
    store = await _create_store(
        api_client,
        headers,
        name="SKU 归属店",
        external_id="sku-store-2",
    )
    first_product = await _create_product(
        api_client, headers, store_id=store["id"], name="SKU 商品一"
    )
    second_product = await _create_product(
        api_client, headers, store_id=store["id"], name="SKU 商品二"
    )
    sku = await _create_sku(api_client, headers, product_id=first_product["id"])

    inventory = db_session.scalar(select(InventoryItem).where(InventoryItem.sku_id == sku["id"]))
    assert inventory is not None
    inventory.stock_qty = 10
    inventory.warning_threshold = 2
    db_session.add(
        InventoryMovement(
            id=1,
            sku_id=sku["id"],
            movement_type="inbound",
            change_qty=10,
            before_qty=0,
            after_qty=10,
            reason_text="初始入库",
            created_by=admin.id,
        )
    )
    db_session.commit()

    cross_product = await api_client.get(
        f"/api/v1/products/{second_product['id']}/skus/{sku['id']}",
        headers=headers,
    )
    assert cross_product.status_code == 404
    assert cross_product.json()["code"] == "SKU_NOT_FOUND"

    disable_response = await api_client.patch(
        f"/api/v1/products/{first_product['id']}/skus/{sku['id']}/status",
        headers=headers,
        json={"status": "inactive"},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "inactive"

    db_session.expire_all()
    persisted_sku = db_session.get(ProductSku, sku["id"])
    movement_count = db_session.scalar(
        select(func.count(InventoryMovement.id)).where(InventoryMovement.sku_id == sku["id"])
    )
    assert persisted_sku is not None
    assert persisted_sku.status == "inactive"
    assert movement_count == 1


async def test_sku_permissions_and_inactive_product_are_enforced(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    create_test_user(
        db_session,
        username="viewer",
        password=VIEWER_PASSWORD,
        role="viewer",
    )
    admin_token = await login(api_client, "admin", ADMIN_PASSWORD)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    store = await _create_store(
        api_client,
        admin_headers,
        name="SKU 权限店",
        external_id="sku-store-3",
    )
    product = await _create_product(
        api_client, admin_headers, store_id=store["id"], name="SKU 权限商品"
    )
    sku = await _create_sku(
        api_client,
        admin_headers,
        product_id=product["id"],
        status="inactive",
    )
    await api_client.delete(f"/api/v1/products/{product['id']}", headers=admin_headers)

    activate_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/skus/{sku['id']}/status",
        headers=admin_headers,
        json={"status": "active"},
    )
    assert activate_response.status_code == 409
    assert activate_response.json()["code"] == "PRODUCT_INACTIVE"

    viewer_token = await login(api_client, "viewer", VIEWER_PASSWORD)
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    forbidden = await api_client.post(
        f"/api/v1/products/{product['id']}/skus",
        headers=viewer_headers,
        json={"sku_code": "VIEWER-SKU", "sku_name": "无权限", "price": 1},
    )
    assert forbidden.status_code == 403
    readable = await api_client.get(
        f"/api/v1/products/{product['id']}/skus", headers=viewer_headers
    )
    assert readable.status_code == 200
