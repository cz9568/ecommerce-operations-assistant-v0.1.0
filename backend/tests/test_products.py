from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from backend.app.models.entities import ProductDiagnosis, ReviewReport
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)


async def _create_store(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    external_id: str,
    status: str = "active",
) -> dict:
    response = await client.post(
        "/api/v1/stores",
        headers=headers,
        json={
            "store_name": name,
            "platform": "tmall",
            "external_store_id": external_id,
            "status": status,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_product(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    store_id: int,
    name: str,
) -> dict:
    response = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "store_id": store_id,
            "name": name,
            "category": "家居",
            "price": "99.90",
            "cost": "45.25",
            "target_audience": "租房用户",
            "selling_points": "轻量、耐用",
            "product_url": "https://example.com/products/1001",
            "images": ["https://example.com/images/1001.jpg"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_product_crud_filters_status_and_recent_activity(
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
        name="商品测试店",
        external_id="product-store-1",
    )
    product = await _create_product(
        api_client,
        headers,
        store_id=store["id"],
        name="折叠收纳架",
    )
    assert product["platform"] == "tmall"
    assert product["status"] == "draft"
    assert product["store_name"] == "商品测试店"

    now = datetime.now(UTC)
    db_session.add_all(
        [
            ProductDiagnosis(product_id=product["id"], created_at=now - timedelta(days=2)),
            ProductDiagnosis(product_id=product["id"], created_at=now - timedelta(days=1)),
            ReviewReport(
                product_id=product["id"],
                period_start=date(2026, 9, 1),
                period_end=date(2026, 9, 7),
                created_at=now - timedelta(hours=2),
            ),
        ]
    )
    db_session.commit()

    list_response = await api_client.get(
        f"/api/v1/products?store_id={store['id']}&platform=tmall&status=draft&q=收纳",
        headers=headers,
    )
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["total"] == 1
    assert list_body["items"][0]["last_diagnosis_at"] is not None
    assert list_body["items"][0]["last_review_at"] is not None

    invalid_price = await api_client.patch(
        f"/api/v1/products/{product['id']}",
        headers=headers,
        json={"price": "-0.01"},
    )
    assert invalid_price.status_code == 422

    update_response = await api_client.patch(
        f"/api/v1/products/{product['id']}",
        headers=headers,
        json={"price": "109.90", "cost": None, "images": []},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["price"] == "109.90"
    assert update_response.json()["cost"] is None
    assert update_response.json()["images"] == []

    activate_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["status"] == "active"

    delete_response = await api_client.delete(f"/api/v1/products/{product['id']}", headers=headers)
    assert delete_response.status_code == 204
    archived_response = await api_client.get(f"/api/v1/products/{product['id']}", headers=headers)
    assert archived_response.status_code == 200
    assert archived_response.json()["status"] == "inactive"


async def test_product_permissions_and_store_status_are_enforced(
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
    inactive_store = await _create_store(
        api_client,
        admin_headers,
        name="停用店铺",
        external_id="inactive-product-store",
        status="inactive",
    )

    inactive_response = await api_client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={"store_id": inactive_store["id"], "name": "不能创建", "price": 1},
    )
    assert inactive_response.status_code == 409
    assert inactive_response.json()["code"] == "STORE_INACTIVE"

    viewer_token = await login(api_client, "viewer", VIEWER_PASSWORD)
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    forbidden = await api_client.post(
        "/api/v1/products",
        headers=viewer_headers,
        json={"store_id": inactive_store["id"], "name": "无权限", "price": 1},
    )
    assert forbidden.status_code == 403
    readable = await api_client.get("/api/v1/products", headers=viewer_headers)
    assert readable.status_code == 200


async def test_mapping_uniqueness_and_cross_product_access_are_enforced(
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
    first_store = await _create_store(
        api_client,
        headers,
        name="映射店铺一",
        external_id="mapping-store-1",
    )
    second_store = await _create_store(
        api_client,
        headers,
        name="映射店铺二",
        external_id="mapping-store-2",
    )
    first_product = await _create_product(
        api_client, headers, store_id=first_store["id"], name="商品一"
    )
    sibling_product = await _create_product(
        api_client, headers, store_id=first_store["id"], name="商品二"
    )
    other_store_product = await _create_product(
        api_client, headers, store_id=second_store["id"], name="商品三"
    )
    mapping_payload = {
        "platform_product_id": "TMALL-P-100",
        "platform_sku_id": "TMALL-SKU-1",
    }

    create_response = await api_client.post(
        f"/api/v1/products/{first_product['id']}/mappings",
        headers=headers,
        json=mapping_payload,
    )
    assert create_response.status_code == 201, create_response.text
    mapping = create_response.json()
    assert mapping["store_id"] == first_store["id"]
    assert mapping["platform"] == "tmall"

    conflict = await api_client.post(
        f"/api/v1/products/{sibling_product['id']}/mappings",
        headers=headers,
        json=mapping_payload,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "PLATFORM_MAPPING_EXISTS"

    other_store_allowed = await api_client.post(
        f"/api/v1/products/{other_store_product['id']}/mappings",
        headers=headers,
        json=mapping_payload,
    )
    assert other_store_allowed.status_code == 201

    cross_product_update = await api_client.patch(
        f"/api/v1/products/{sibling_product['id']}/mappings/{mapping['id']}",
        headers=headers,
        json={"mapping_status": "inactive"},
    )
    assert cross_product_update.status_code == 404
    assert cross_product_update.json()["code"] == "PRODUCT_MAPPING_NOT_FOUND"

    update_response = await api_client.patch(
        f"/api/v1/products/{first_product['id']}/mappings/{mapping['id']}",
        headers=headers,
        json={"mapping_status": "inactive"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["mapping_status"] == "inactive"

    cross_product_delete = await api_client.delete(
        f"/api/v1/products/{sibling_product['id']}/mappings/{mapping['id']}",
        headers=headers,
    )
    assert cross_product_delete.status_code == 404

    delete_response = await api_client.delete(
        f"/api/v1/products/{first_product['id']}/mappings/{mapping['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 204
