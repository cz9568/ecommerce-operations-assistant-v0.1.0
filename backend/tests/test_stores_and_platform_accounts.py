import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.entities import InventoryItem, PlatformAccount, Product, ProductSku
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
    owner_user_id: int | None = None,
) -> dict:
    response = await client.post(
        "/api/v1/stores",
        headers=headers,
        json={
            "store_name": "旗舰测试店",
            "platform": "tmall",
            "external_store_id": "store-1001",
            "owner_user_id": owner_user_id,
            "remark": "M2 测试店铺",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_store_crud_filters_and_aggregate_counts(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    owner = create_test_user(
        db_session,
        username="operator",
        password="Strong-Operator-Password-123",
        role="operator",
    )
    token = await login(api_client, "admin", ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}
    store_data = await _create_store(api_client, headers, owner_user_id=owner.id)
    store_id = store_data["id"]
    assert store_data["owner_name"] == "Operator"

    product = Product(
        store_id=store_id,
        name="测试商品",
        platform="tmall",
        price=99,
        status="active",
    )
    db_session.add(product)
    db_session.flush()
    low_sku = ProductSku(
        product_id=product.id,
        sku_code="LOW-1",
        sku_name="低库存 SKU",
        price=99,
        status="active",
    )
    enough_sku = ProductSku(
        product_id=product.id,
        sku_code="ENOUGH-1",
        sku_name="充足库存 SKU",
        price=99,
        status="active",
    )
    db_session.add_all([low_sku, enough_sku])
    db_session.flush()
    db_session.add_all(
        [
            InventoryItem(sku_id=low_sku.id, stock_qty=5, locked_qty=1, warning_threshold=5),
            InventoryItem(
                sku_id=enough_sku.id,
                stock_qty=20,
                locked_qty=0,
                warning_threshold=5,
            ),
        ]
    )
    db_session.commit()

    list_response = await api_client.get(
        "/api/v1/stores?platform=tmall&status=active&q=旗舰",
        headers=headers,
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 1
    assert body["items"][0]["product_count"] == 1
    assert body["items"][0]["low_stock_count"] == 1

    summary_response = await api_client.get(f"/api/v1/stores/{store_id}/summary", headers=headers)
    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "store_id": store_id,
        "product_count": 1,
        "sku_count": 2,
        "low_stock_count": 1,
        "platform_account_count": 0,
        "authorized_account_count": 0,
    }

    update_response = await api_client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"status": "inactive", "owner_user_id": None},
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "inactive"
    assert update_response.json()["owner_user_id"] is None


async def test_store_owner_and_permissions_are_enforced(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    create_test_user(
        db_session,
        username="viewer",
        password=VIEWER_PASSWORD,
        role="viewer",
    )
    inactive_owner = create_test_user(
        db_session,
        username="inactive-owner",
        password="Strong-Inactive-Password-123",
        role="operator",
        status="inactive",
    )
    viewer_token = await login(api_client, "viewer", VIEWER_PASSWORD)
    headers = {"Authorization": f"Bearer {viewer_token}"}

    forbidden = await api_client.post(
        "/api/v1/stores",
        headers=headers,
        json={"store_name": "无权限店铺", "platform": "jd"},
    )
    assert forbidden.status_code == 403

    create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    admin_token = await login(api_client, "admin", ADMIN_PASSWORD)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    invalid_owner = await api_client.post(
        "/api/v1/stores",
        headers=admin_headers,
        json={
            "store_name": "负责人无效店铺",
            "platform": "jd",
            "owner_user_id": inactive_owner.id,
        },
    )
    assert invalid_owner.status_code == 409
    assert invalid_owner.json()["code"] == "STORE_OWNER_INACTIVE"

    readable = await api_client.get("/api/v1/stores", headers=headers)
    assert readable.status_code == 200


async def test_platform_account_is_masked_and_authorization_metadata_is_safe(
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
    store = await _create_store(api_client, headers)

    rejected_secret = await api_client.post(
        f"/api/v1/stores/{store['id']}/platform-accounts",
        headers=headers,
        json={"account_name": "13800138000", "password": "must-not-be-accepted"},
    )
    assert rejected_secret.status_code == 422

    create_response = await api_client.post(
        f"/api/v1/stores/{store['id']}/platform-accounts",
        headers=headers,
        json={"account_name": "13800138000", "remark": "主账号"},
    )
    assert create_response.status_code == 201, create_response.text
    account = create_response.json()
    account_id = account["id"]
    assert account["account_name_masked"] == "138****8000"
    assert "account_name" not in account

    start_response = await api_client.post(
        f"/api/v1/platform-accounts/{account_id}/authorization/start",
        headers=headers,
    )
    assert start_response.status_code == 200
    state = start_response.json()["state"]
    db_session.expire_all()
    pending = db_session.get(PlatformAccount, account_id)
    assert pending is not None
    assert pending.auth_meta_json["authorization_state_hash"] != state
    assert state not in str(pending.auth_meta_json)

    list_response = await api_client.get(
        f"/api/v1/stores/{store['id']}/platform-accounts", headers=headers
    )
    serialized = str(list_response.json())
    assert list_response.status_code == 200
    assert "authorization_state_hash" not in serialized
    assert "13800138000" not in serialized

    rejected_callback_secret = await api_client.post(
        f"/api/v1/platform-accounts/{account_id}/authorization/callback",
        json={"state": state, "result": "authorized", "access_token": "plain-secret"},
    )
    assert rejected_callback_secret.status_code == 422

    callback_response = await api_client.post(
        f"/api/v1/platform-accounts/{account_id}/authorization/callback",
        json={
            "state": state,
            "result": "authorized",
            "seller_id": "seller-001",
            "scopes": ["product.read", "order.read"],
            "expires_at": "2027-01-01T00:00:00Z",
        },
    )
    assert callback_response.status_code == 200, callback_response.text
    callback_body = callback_response.json()
    assert callback_body["auth_status"] == "authorized"
    assert callback_body["auth_meta"]["seller_id"] == "seller-001"

    db_session.expire_all()
    authorized = db_session.scalar(select(PlatformAccount).where(PlatformAccount.id == account_id))
    assert authorized is not None
    persisted = str(authorized.auth_meta_json).lower()
    assert "token" not in persisted
    assert "password" not in persisted
    assert "cookie" not in persisted
    assert "authorization_state_hash" not in persisted

    replay = await api_client.post(
        f"/api/v1/platform-accounts/{account_id}/authorization/callback",
        json={"state": state, "result": "authorized"},
    )
    assert replay.status_code == 400
    assert replay.json()["code"] == "INVALID_AUTHORIZATION_STATE"

    revoke_response = await api_client.post(
        f"/api/v1/platform-accounts/{account_id}/authorization/revoke",
        headers=headers,
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["auth_status"] == "revoked"
    assert revoke_response.json()["auth_meta"]["scopes"] == []
    assert all(
        value is None
        for key, value in revoke_response.json()["auth_meta"].items()
        if key != "scopes"
    )
