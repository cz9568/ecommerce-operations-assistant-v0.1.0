import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AuditLog,
    GeneratedAsset,
    GenerationJob,
    InventoryItem,
    SystemSetting,
)
from backend.app.services.settings import resolve_runtime_settings
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)


async def _headers(
    client: httpx.AsyncClient, session: Session
) -> tuple[dict[str, str], dict[str, str]]:
    create_test_user(session, username="admin", password=ADMIN_PASSWORD, role="admin")
    create_test_user(session, username="viewer", password=VIEWER_PASSWORD, role="viewer")
    return (
        {"Authorization": f"Bearer {await login(client, 'admin', ADMIN_PASSWORD)}"},
        {"Authorization": f"Bearer {await login(client, 'viewer', VIEWER_PASSWORD)}"},
    )


async def test_dashboard_aggregates_filters_and_demo_guidance(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin, viewer = await _headers(api_client, db_session)
    empty = await api_client.get("/api/v1/dashboard", headers=viewer)
    assert empty.status_code == 200
    assert empty.json()["metrics"]["product_count"] == 0
    assert empty.json()["has_demo_data"] is False

    seeded = await api_client.post("/api/v1/demo-data/initialize", headers=admin)
    assert seeded.status_code == 200, seeded.text
    inventory = db_session.scalar(select(InventoryItem))
    pending_job = db_session.scalar(
        select(GenerationJob).where(GenerationJob.job_status == "failed")
    )
    pending_asset = db_session.scalar(
        select(GeneratedAsset).where(GeneratedAsset.review_status == "rejected")
    )
    assert inventory and pending_job and pending_asset
    inventory.warning_threshold = 100
    pending_job.job_status = "pending"
    pending_job.progress_percent = 0
    pending_asset.review_status = "pending"
    db_session.commit()

    response = await api_client.get("/api/v1/dashboard?platform=taobao", headers=viewer)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["available_platforms"] == ["taobao"]
    assert data["metrics"] == {
        "store_count": 1,
        "product_count": 1,
        "low_stock_count": 1,
        "active_job_count": 1,
        "pending_asset_count": 1,
        "review_report_count": 1,
    }
    assert data["stores"][0]["product_count"] == 1
    assert data["products"][0]["low_stock_count"] == 1
    assert data["low_stock"][0]["available_qty"] == 80
    assert data["recent_jobs"]
    assert data["recent_reviews"][0]["product_id"] == seeded.json()["product_id"]
    assert data["has_demo_data"] is True
    filtered = await api_client.get("/api/v1/dashboard?platform=jd", headers=viewer)
    assert filtered.json()["metrics"]["product_count"] == 0


async def test_settings_permissions_validation_encryption_and_audit(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin, viewer = await _headers(api_client, db_session)
    assert (await api_client.get("/api/v1/settings", headers=viewer)).status_code == 403
    initial = await api_client.get("/api/v1/settings", headers=admin)
    assert initial.status_code == 200
    secret = next(
        item for item in initial.json()["groups"]["model"] if item["key"] == "llm_api_key"
    )
    assert secret["value"] is None

    invalid = await api_client.patch(
        "/api/v1/settings/queue",
        headers=admin,
        json={"values": {"job_worker_concurrency": 99}},
    )
    assert invalid.status_code == 422
    updated = await api_client.patch(
        "/api/v1/settings/model",
        headers=admin,
        json={
            "values": {
                "llm_model": "mock",
                "generation_provider": "mock",
                "llm_api_key": "sk-sensitive-test-value",
            }
        },
    )
    assert updated.status_code == 200, updated.text
    serialized = json.dumps(updated.json(), ensure_ascii=False)
    assert "sk-sensitive-test-value" not in serialized
    secret_after = next(
        item for item in updated.json()["groups"]["model"] if item["key"] == "llm_api_key"
    )
    assert secret_after["configured"] is True
    assert secret_after["source"] == "database"
    assert secret_after["value"] is None

    row = db_session.scalar(select(SystemSetting).where(SystemSetting.setting_key == "llm_api_key"))
    assert row is not None
    assert "sk-sensitive-test-value" not in json.dumps(row.value_json)
    assert resolve_runtime_settings(db_session).llm_api_key.get_secret_value() == (
        "sk-sensitive-test-value"
    )
    audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "settings.update"))
    assert audit is not None
    assert audit.detail_json["contains_sensitive"] is True
    assert "sk-sensitive-test-value" not in json.dumps(audit.detail_json)
