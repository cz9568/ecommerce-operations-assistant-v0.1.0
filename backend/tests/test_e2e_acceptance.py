import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.entities import ProductDiagnosis
from backend.tests.test_auth_and_users import ADMIN_PASSWORD, create_test_user, login

OPERATOR_PASSWORD = "Strong-Operator-Password-123"
VIEWER_PASSWORD = "Strong-Viewer-Password-123"


async def _role_headers(
    client: httpx.AsyncClient, session: Session
) -> dict[str, dict[str, str]]:
    for username, password, role in (
        ("admin", ADMIN_PASSWORD, "admin"),
        ("operator", OPERATOR_PASSWORD, "operator"),
        ("viewer", VIEWER_PASSWORD, "viewer"),
    ):
        create_test_user(session, username=username, password=password, role=role)
    return {
        username: {"Authorization": f"Bearer {await login(client, username, password)}"}
        for username, password in (
            ("admin", ADMIN_PASSWORD),
            ("operator", OPERATOR_PASSWORD),
            ("viewer", VIEWER_PASSWORD),
        )
    }


async def test_three_roles_and_complete_single_product_demo_chain(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    """Release E2E: authenticate all roles and traverse the complete demo business chain."""
    headers = await _role_headers(api_client, db_session)
    for role in ("admin", "operator", "viewer"):
        me = await api_client.get("/api/v1/auth/me", headers=headers[role])
        assert me.status_code == 200
        assert me.json()["role"] == role

    assert (await api_client.get("/api/v1/dashboard")).status_code == 401
    assert (await api_client.get("/api/v1/users", headers=headers["operator"])).status_code == 403
    operator_settings = await api_client.get("/api/v1/settings", headers=headers["operator"])
    assert operator_settings.status_code == 403
    assert (
        await api_client.post("/api/v1/demo-data/initialize", headers=headers["viewer"])
    ).status_code == 403

    seeded_response = await api_client.post(
        "/api/v1/demo-data/initialize", headers=headers["admin"]
    )
    assert seeded_response.status_code == 200, seeded_response.text
    seeded = seeded_response.json()
    product_id = seeded["product_id"]
    store_id = seeded["store_id"]
    sku_id = seeded["sku_id"]
    object_ids = seeded["object_ids"]

    dashboard = await api_client.get("/api/v1/dashboard?platform=taobao", headers=headers["viewer"])
    assert dashboard.status_code == 200
    assert dashboard.json()["has_demo_data"] is True
    assert dashboard.json()["metrics"]["product_count"] == 1

    checks = (
        (f"/api/v1/stores/{store_id}", None),
        (f"/api/v1/products/{product_id}", None),
        (f"/api/v1/products/{product_id}/skus", "items"),
        (f"/api/v1/products/{product_id}/skus/{sku_id}/inventory", None),
        (f"/api/v1/products/{product_id}/skus/{sku_id}/inventory/movements", "items"),
        (f"/api/v1/products/{product_id}/competitors", "items"),
        (f"/api/v1/products/{product_id}/diagnoses", "items"),
        (f"/api/v1/products/{product_id}/creative-plans?plan_type=main_image", "items"),
        (f"/api/v1/products/{product_id}/generation-jobs", "items"),
        (f"/api/v1/products/{product_id}/assets", "items"),
        (f"/api/v1/products/{product_id}/promotion-links", "items"),
        (f"/api/v1/products/{product_id}/ad-recommendations", "items"),
        (f"/api/v1/products/{product_id}/ad-experiments", "items"),
        (f"/api/v1/products/{product_id}/performance-records", "items"),
        (f"/api/v1/products/{product_id}/performance-records/summary", None),
        (f"/api/v1/products/{product_id}/review-reports", "items"),
    )
    for path, collection_key in checks:
        response = await api_client.get(path, headers=headers["viewer"])
        assert response.status_code == 200, f"{path}: {response.text}"
        if collection_key:
            assert response.json()[collection_key], f"{path} returned an empty chain segment"

    events = await api_client.get(
        f"/api/v1/products/{product_id}/generation-jobs/{object_ids['generation_job']}/events",
        headers=headers["viewer"],
    )
    assert events.status_code == 200
    assert events.json()
    revisions = await api_client.get(
        f"/api/v1/products/{product_id}/review-reports/{object_ids['review_report']}/revisions",
        headers=headers["viewer"],
    )
    assert revisions.status_code == 200
    assert revisions.json()

    next_diagnosis = db_session.scalar(
        select(ProductDiagnosis).where(
            ProductDiagnosis.product_id == product_id,
            ProductDiagnosis.source_review_report_id == object_ids["review_report"],
        )
    )
    assert next_diagnosis is not None

    viewer_write = await api_client.post(
        f"/api/v1/products/{product_id}/diagnoses/generate",
        headers=headers["viewer"],
        json={},
    )
    assert viewer_write.status_code == 403
    operator_read = await api_client.get(
        f"/api/v1/products/{product_id}/assets", headers=headers["operator"]
    )
    assert operator_read.status_code == 200

    repeated = await api_client.post(
        "/api/v1/demo-data/initialize", headers=headers["admin"]
    )
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["product_id"] == product_id
