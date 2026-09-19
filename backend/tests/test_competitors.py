from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.entities import CompetitorMonitor
from backend.app.services import competitors as competitor_service
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_product, _create_store


async def _setup_product(
    api_client: httpx.AsyncClient, db_session: Session, *, suffix: str
) -> tuple[dict[str, str], dict]:
    create_test_user(
        db_session,
        username=f"admin-{suffix}",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    token = await login(api_client, f"admin-{suffix}", ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}
    store = await _create_store(
        api_client,
        headers,
        name=f"竞品店铺-{suffix}",
        external_id=f"competitor-store-{suffix}",
    )
    product = await _create_product(
        api_client,
        headers,
        store_id=store["id"],
        name=f"目标商品-{suffix}",
    )
    return headers, product


async def _create_competitor(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_id: int,
    *,
    name: str = "竞品 A",
    url: str = "https://detail.tmall.com/item.htm?id=100",
) -> dict:
    response = await client.post(
        f"/api/v1/products/{product_id}/competitors",
        headers=headers,
        json={
            "name": name,
            "platform": "tmall",
            "url": url,
            "price": "88.00",
            "sales_hint": "月销 1000+",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_competitor_crud_scope_allowlist_and_permissions(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    headers, product = await _setup_product(api_client, db_session, suffix="crud")
    competitor = await _create_competitor(api_client, headers, product["id"])
    assert competitor["field_sources"]["price"] == "manual"

    listing = await api_client.get(
        f"/api/v1/products/{product['id']}/competitors?q=竞品&status=active",
        headers=headers,
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    update = await api_client.patch(
        f"/api/v1/products/{product['id']}/competitors/{competitor['id']}",
        headers=headers,
        json={"price": "79.90", "review_keywords": "安装简单"},
    )
    assert update.status_code == 200
    assert update.json()["price"] == "79.90"

    blocked = await api_client.post(
        f"/api/v1/products/{product['id']}/competitors",
        headers=headers,
        json={
            "name": "非白名单",
            "platform": "other",
            "url": "https://example.com/item/1",
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "PUBLIC_URL_DOMAIN_NOT_ALLOWED"

    other_store = await _create_store(
        api_client,
        headers,
        name="其他店铺",
        external_id="competitor-other-store",
    )
    other_product = await _create_product(
        api_client, headers, store_id=other_store["id"], name="其他商品"
    )
    cross_product = await api_client.get(
        f"/api/v1/products/{other_product['id']}/competitors/{competitor['id']}",
        headers=headers,
    )
    assert cross_product.status_code == 404

    create_test_user(
        db_session,
        username="viewer-competitor",
        password=VIEWER_PASSWORD,
        role="viewer",
    )
    viewer_token = await login(api_client, "viewer-competitor", VIEWER_PASSWORD)
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    readable = await api_client.get(
        f"/api/v1/products/{product['id']}/competitors", headers=viewer_headers
    )
    assert readable.status_code == 200
    forbidden = await api_client.patch(
        f"/api/v1/products/{product['id']}/competitors/{competitor['id']}",
        headers=viewer_headers,
        json={"price": "1.00"},
    )
    assert forbidden.status_code == 403

    archived = await api_client.delete(
        f"/api/v1/products/{product['id']}/competitors/{competitor['id']}",
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "inactive"


async def test_public_link_parse_success_failure_retry_and_apply(
    api_client: httpx.AsyncClient, db_session: Session, monkeypatch
) -> None:
    headers, product = await _setup_product(api_client, db_session, suffix="parse")
    competitor = await _create_competitor(api_client, headers, product["id"])

    def successful_fetch(_url: str):
        return (
            {
                "title": "解析标题",
                "price": Decimal("66.60"),
                "sales_hint": "已售 2000+",
                "main_image": "https://img.alicdn.com/example.jpg",
                "selling_points": "公开页面描述",
                "review_keywords": None,
            },
            "https://detail.tmall.com/item.htm?id=100",
            200,
        )

    monkeypatch.setattr(competitor_service, "_fetch_public_metadata", successful_fetch)
    create = await api_client.post(
        f"/api/v1/products/{product['id']}/competitors/import-url-tasks",
        headers=headers,
        json={"source_url": competitor["url"], "competitor_id": competitor["id"]},
    )
    assert create.status_code == 201
    task = create.json()
    run = await api_client.post(
        f"/api/v1/products/{product['id']}/link-parse-tasks/{task['id']}/run",
        headers=headers,
    )
    assert run.status_code == 200
    assert run.json()["task_status"] == "succeeded"
    assert run.json()["result"]["title"] == "解析标题"

    apply = await api_client.post(
        f"/api/v1/products/{product['id']}/link-parse-tasks/{task['id']}/apply",
        headers=headers,
        json={
            "competitor_id": competitor["id"],
            "fields": ["title", "price", "sales_hint", "main_image"],
        },
    )
    assert apply.status_code == 200, apply.text
    applied = apply.json()
    assert applied["price"] == "66.60"
    assert applied["field_sources"]["price"] == "parsed"
    assert applied["last_parsed_at"] is not None

    def restricted_fetch(_url: str):
        raise competitor_service.ParseFailure(
            "CHALLENGE_OR_LOGIN_REQUIRED", "页面出现登录或验证码，系统不会尝试绕过"
        )

    monkeypatch.setattr(competitor_service, "_fetch_public_metadata", restricted_fetch)
    failed_create = await api_client.post(
        f"/api/v1/products/{product['id']}/competitors/import-url-tasks",
        headers=headers,
        json={"source_url": competitor["url"]},
    )
    failed_task = failed_create.json()
    failed_run = await api_client.post(
        f"/api/v1/products/{product['id']}/link-parse-tasks/{failed_task['id']}/run",
        headers=headers,
    )
    assert failed_run.status_code == 200
    assert failed_run.json()["task_status"] == "failed"
    assert failed_run.json()["error_code"] == "CHALLENGE_OR_LOGIN_REQUIRED"

    failed_apply = await api_client.post(
        f"/api/v1/products/{product['id']}/link-parse-tasks/{failed_task['id']}/apply",
        headers=headers,
        json={"competitor_id": competitor["id"], "fields": ["price"]},
    )
    assert failed_apply.status_code == 409


async def test_monitor_snapshots_changes_backoff_and_locking(
    api_client: httpx.AsyncClient, db_session: Session, monkeypatch
) -> None:
    headers, product = await _setup_product(api_client, db_session, suffix="monitor")
    competitor = await _create_competitor(api_client, headers, product["id"])
    values = [Decimal("80.00"), Decimal("75.00")]

    def changing_fetch(_url: str):
        price = values.pop(0)
        return (
            {
                "title": "监控标题",
                "price": price,
                "sales_hint": "月销变化",
                "main_image": None,
                "selling_points": "监控描述",
                "review_keywords": None,
            },
            competitor["url"],
            200,
        )

    monkeypatch.setattr(competitor_service, "_fetch_public_metadata", changing_fetch)
    config = await api_client.post(
        f"/api/v1/products/{product['id']}/competitors/{competitor['id']}/monitor",
        headers=headers,
        json={"monitor_status": "active", "interval_minutes": 60},
    )
    assert config.status_code == 200
    monitor_id = config.json()["id"]

    for _ in range(2):
        run = await api_client.post(
            f"/api/v1/products/{product['id']}/competitors/{competitor['id']}/monitor/run",
            headers=headers,
        )
        assert run.status_code == 200, run.text

    snapshots = await api_client.get(
        f"/api/v1/products/{product['id']}/competitors/{competitor['id']}/monitor/snapshots",
        headers=headers,
    )
    assert snapshots.status_code == 200
    assert snapshots.json()["total"] == 2
    latest = snapshots.json()["items"][0]
    assert latest["price"] == "75.00"
    assert "price" in latest["changed_fields"]

    apply = await api_client.post(
        f"/api/v1/products/{product['id']}/competitors/{competitor['id']}/monitor/snapshots/{latest['id']}/apply",
        headers=headers,
        json={"fields": ["price", "title"]},
    )
    assert apply.status_code == 200
    assert apply.json()["field_sources"]["price"] == "monitor"

    monitor = db_session.get(CompetitorMonitor, monitor_id)
    assert monitor is not None
    monitor.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
    monitor.lock_token = "already-running"
    monitor.locked_until = datetime.now(UTC) + timedelta(minutes=5)
    db_session.commit()
    locked = await api_client.post("/api/v1/workspace/competitor-monitors/run-due", headers=headers)
    assert locked.status_code == 200
    assert locked.json()["claimed_count"] == 0

    def failing_fetch(_url: str):
        raise competitor_service.ParseFailure("FETCH_TIMEOUT", "公开链接访问超时")

    monitor = db_session.scalar(select(CompetitorMonitor).where(CompetitorMonitor.id == monitor_id))
    assert monitor is not None
    monitor.lock_token = None
    monitor.locked_until = None
    db_session.commit()
    monkeypatch.setattr(competitor_service, "_fetch_public_metadata", failing_fetch)
    failed = await api_client.post(
        f"/api/v1/products/{product['id']}/competitors/{competitor['id']}/monitor/run",
        headers=headers,
    )
    assert failed.status_code == 200
    assert failed.json()["consecutive_failures"] == 1
    assert failed.json()["last_error_code"] == "FETCH_TIMEOUT"
