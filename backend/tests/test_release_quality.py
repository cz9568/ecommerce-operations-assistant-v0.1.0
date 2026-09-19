from time import perf_counter

import httpx
from sqlalchemy import event
from sqlalchemy.orm import Session

from backend.tests.conftest import test_engine
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_store


async def _headers(
    client: httpx.AsyncClient, session: Session
) -> tuple[dict[str, str], dict[str, str]]:
    create_test_user(session, username="admin", password=ADMIN_PASSWORD, role="admin")
    create_test_user(session, username="viewer", password=VIEWER_PASSWORD, role="viewer")
    return (
        {"Authorization": f"Bearer {await login(client, 'admin', ADMIN_PASSWORD)}"},
        {"Authorization": f"Bearer {await login(client, 'viewer', VIEWER_PASSWORD)}"},
    )


async def test_dashboard_query_count_is_bounded(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin, viewer = await _headers(api_client, db_session)
    seeded = await api_client.post("/api/v1/demo-data/initialize", headers=admin)
    assert seeded.status_code == 200
    statements: list[str] = []

    def record_statement(*args) -> None:
        statements.append(str(args[2]))

    event.listen(test_engine, "before_cursor_execute", record_statement)
    try:
        response = await api_client.get("/api/v1/dashboard", headers=viewer)
    finally:
        event.remove(test_engine, "before_cursor_execute", record_statement)
    assert response.status_code == 200
    # Two authentication queries plus eleven constant aggregate/list queries.
    assert len(statements) <= 13, statements


async def test_maximum_import_preview_is_bounded_and_repeatable(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin, _viewer = await _headers(api_client, db_session)
    store = await _create_store(
        api_client, admin, name="容量基线店", external_id="release-capacity-store"
    )
    header = (
        "store_id,name,category,price,cost,status,target_audience,"
        "selling_points,product_url,images\n"
    )
    rows = [
        f"{store['id']},容量商品{i},测试,99,50,active,用户,卖点,https://example.com/p/{i},\n"
        for i in range(1000)
    ]
    content = (header + "".join(rows)).encode()
    started = perf_counter()
    response = await api_client.post(
        "/api/v1/imports/products/upload?filename=capacity.csv",
        content=content,
        headers={**admin, "X-Idempotency-Key": "release-capacity-1000"},
    )
    duration = perf_counter() - started
    assert response.status_code == 200, response.text
    assert response.json()["batch"]["total_rows"] == 1000
    assert response.json()["batch"]["valid_rows"] == 1000
    assert duration < 15

    repeated = await api_client.post(
        "/api/v1/imports/products/upload?filename=capacity.csv",
        content=content,
        headers={**admin, "X-Idempotency-Key": "release-capacity-1000"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["batch"]["id"] == response.json()["batch"]["id"]

    too_many = (header + "".join(rows) + rows[0]).encode()
    rejected = await api_client.post(
        "/api/v1/imports/products/upload?filename=too-many.csv",
        content=too_many,
        headers={**admin, "X-Idempotency-Key": "release-capacity-1001"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "IMPORT_ROW_COUNT_INVALID"


async def test_authentication_input_and_role_boundaries(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin, viewer = await _headers(api_client, db_session)
    protected_paths = (
        "/api/v1/dashboard",
        "/api/v1/stores",
        "/api/v1/products",
        "/api/v1/inventory",
        "/api/v1/imports",
        "/api/v1/settings",
    )
    for path in protected_paths:
        response = await api_client.get(path)
        assert response.status_code == 401, path
        assert response.json()["code"] == "AUTHENTICATION_REQUIRED"

    assert (await api_client.get("/api/v1/users", headers=viewer)).status_code == 403
    assert (await api_client.get("/api/v1/settings", headers=viewer)).status_code == 403
    assert (
        await api_client.post(
            "/api/v1/stores",
            headers=viewer,
            json={"store_name": "越权店铺", "platform": "taobao"},
        )
    ).status_code == 403

    injection = await api_client.get(
        "/api/v1/products", headers=admin, params={"q": "%' OR 1=1 --"}
    )
    assert injection.status_code == 200
    assert injection.json()["total"] == 0
    invalid_request_id = await api_client.get(
        "/api/v1/dashboard",
        headers={**admin, "X-Request-ID": "bad\r\nX-Forged: yes"},
    )
    assert invalid_request_id.status_code == 200
    assert invalid_request_id.headers["X-Request-ID"] != "bad\r\nX-Forged: yes"
    assert "\r" not in invalid_request_id.headers["X-Request-ID"]
