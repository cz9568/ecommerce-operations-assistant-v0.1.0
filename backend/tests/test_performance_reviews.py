import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.integrations.ai import MockTextProvider
from backend.app.models.entities import (
    AdExperiment,
    AdRecommendation,
    AiUsageLog,
    AuditLog,
    CreativePlan,
    GeneratedAsset,
    PromotionLink,
    ReviewReportRevision,
)
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_product, _create_store


async def _context(
    client: httpx.AsyncClient, session: Session
) -> tuple[dict, dict, dict[str, str], dict[str, str]]:
    create_test_user(session, username="admin", password=ADMIN_PASSWORD, role="admin")
    create_test_user(session, username="viewer", password=VIEWER_PASSWORD, role="viewer")
    admin_headers = {"Authorization": f"Bearer {await login(client, 'admin', ADMIN_PASSWORD)}"}
    viewer_headers = {"Authorization": f"Bearer {await login(client, 'viewer', VIEWER_PASSWORD)}"}
    store = await _create_store(
        client,
        admin_headers,
        name="复盘测试店",
        external_id="review-store-1",
    )
    product = await _create_product(
        client,
        admin_headers,
        store_id=store["id"],
        name="复盘测试商品",
    )
    sibling = await _create_product(
        client,
        admin_headers,
        store_id=store["id"],
        name="相邻商品",
    )
    return product, sibling, admin_headers, viewer_headers


def _record_payload(**overrides) -> dict:
    payload = {
        "period_start": "2026-09-01",
        "period_end": "2026-09-07",
        "impressions": 1000,
        "clicks": 100,
        "conversions": 20,
        "spend": "200.00",
        "revenue": "600.00",
        "notes": "首周实验",
    }
    payload.update(overrides)
    return payload


async def test_performance_crud_metrics_scope_overlap_and_void(
    api_client: httpx.AsyncClient,
    db_session: Session,
) -> None:
    product, sibling, admin_headers, viewer_headers = await _context(api_client, db_session)
    plan = CreativePlan(
        product_id=product["id"],
        plan_type="main_image",
        title="经营方案",
        content_json={"title": "经营方案"},
        status="selected",
        version_no=1,
    )
    sibling_plan = CreativePlan(
        product_id=sibling["id"],
        plan_type="main_image",
        title="其他商品方案",
        content_json={"title": "其他商品方案"},
        status="draft",
        version_no=1,
    )
    db_session.add_all([plan, sibling_plan])
    db_session.flush()
    asset = GeneratedAsset(
        product_id=product["id"],
        creative_plan_id=plan.id,
        source_asset_index=0,
        asset_type="image",
        storage_key="products/review/asset.png",
        file_size_bytes=100,
        file_status="available",
        review_status="approved",
        version_no=1,
        lock_version=1,
    )
    link = PromotionLink(
        product_id=product["id"],
        link_name="经营链接",
        target_url="https://example.com/product",
        tracking_code="performance-test-code",
        status="active",
        click_count=0,
        lock_version=1,
    )
    recommendation = AdRecommendation(
        product_id=product["id"], confirm_status="confirmed", version_no=2
    )
    db_session.add_all([asset, link, recommendation])
    db_session.flush()
    experiment = AdExperiment(
        product_id=product["id"],
        recommendation_id=recommendation.id,
        related_asset_id=asset.id,
        related_link_id=link.id,
        experiment_name="经营实验",
        budget_amount="200.00",
        experiment_status="running",
        version_no=3,
    )
    db_session.add(experiment)
    db_session.commit()

    viewer_create = await api_client.post(
        f"/api/v1/products/{product['id']}/performance-records",
        headers=viewer_headers,
        json=_record_payload(),
    )
    assert viewer_create.status_code == 403
    invalid = await api_client.post(
        f"/api/v1/products/{product['id']}/performance-records",
        headers=admin_headers,
        json=_record_payload(impressions=10, clicks=11),
    )
    assert invalid.status_code == 422
    cross_scope = await api_client.post(
        f"/api/v1/products/{product['id']}/performance-records",
        headers=admin_headers,
        json=_record_payload(creative_plan_id=sibling_plan.id),
    )
    assert cross_scope.status_code == 422

    created_response = await api_client.post(
        f"/api/v1/products/{product['id']}/performance-records",
        headers=admin_headers,
        json=_record_payload(
            creative_plan_id=plan.id,
            generated_asset_id=asset.id,
            promotion_link_id=link.id,
            experiment_id=experiment.id,
        ),
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    assert created["ctr"] == "0.100000"
    assert created["conversion_rate"] == "0.200000"
    assert created["roi"] == "3.000000"

    overlap = await api_client.post(
        f"/api/v1/products/{product['id']}/performance-records",
        headers=admin_headers,
        json=_record_payload(period_start="2026-09-07", period_end="2026-09-14"),
    )
    assert overlap.status_code == 409
    assert overlap.json()["code"] == "PERFORMANCE_PERIOD_OVERLAP"

    updated_payload = _record_payload(
        creative_plan_id=plan.id,
        generated_asset_id=asset.id,
        promotion_link_id=link.id,
        experiment_id=experiment.id,
        revenue="800.00",
        expected_version=created["version_no"],
    )
    updated_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/performance-records/{created['id']}",
        headers=admin_headers,
        json=updated_payload,
    )
    assert updated_response.status_code == 200, updated_response.text
    updated = updated_response.json()
    assert updated["roi"] == "4.000000"
    stale = await api_client.patch(
        f"/api/v1/products/{product['id']}/performance-records/{created['id']}",
        headers=admin_headers,
        json=updated_payload,
    )
    assert stale.status_code == 409

    summary = await api_client.get(
        f"/api/v1/products/{product['id']}/performance-records/summary",
        headers=viewer_headers,
    )
    assert summary.status_code == 200
    assert summary.json()["record_count"] == 1
    assert summary.json()["roi"] == "4.000000"
    voided = await api_client.delete(
        f"/api/v1/products/{product['id']}/performance-records/{created['id']}",
        headers=admin_headers,
        params={"expected_version": updated["version_no"]},
    )
    assert voided.status_code == 200
    assert voided.json()["record_status"] == "voided"
    empty_summary = await api_client.get(
        f"/api/v1/products/{product['id']}/performance-records/summary",
        headers=viewer_headers,
    )
    assert empty_summary.json()["record_count"] == 0
    replacement = await api_client.post(
        f"/api/v1/products/{product['id']}/performance-records",
        headers=admin_headers,
        json=_record_payload(),
    )
    assert replacement.status_code == 201


async def test_review_generation_edit_revisions_and_diagnosis_closure(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
) -> None:
    product, sibling, admin_headers, viewer_headers = await _context(api_client, db_session)
    record = await api_client.post(
        f"/api/v1/products/{product['id']}/performance-records",
        headers=admin_headers,
        json=_record_payload(),
    )
    assert record.status_code == 201
    monkeypatch.setattr("backend.app.services.review_reports.get_text_provider", MockTextProvider)
    monkeypatch.setattr("backend.app.services.diagnoses.get_text_provider", MockTextProvider)

    no_data = await api_client.post(
        f"/api/v1/products/{sibling['id']}/review-reports/generate",
        headers=admin_headers,
        json={"period_start": "2026-09-01", "period_end": "2026-09-07"},
    )
    assert no_data.status_code == 422
    assert no_data.json()["code"] == "REVIEW_NO_PERFORMANCE_DATA"
    viewer_generate = await api_client.post(
        f"/api/v1/products/{product['id']}/review-reports/generate",
        headers=viewer_headers,
        json={"period_start": "2026-09-01", "period_end": "2026-09-07"},
    )
    assert viewer_generate.status_code == 403

    generated_response = await api_client.post(
        f"/api/v1/products/{product['id']}/review-reports/generate",
        headers=admin_headers,
        json={
            "period_start": "2026-09-01",
            "period_end": "2026-09-07",
            "notes": "重点复盘首轮实验",
        },
    )
    assert generated_response.status_code == 200, generated_response.text
    report = generated_response.json()
    assert report["version_no"] == 1
    assert report["input_snapshot"]["aggregate"]["record_count"] == 1
    assert report["follow_up_diagnoses"] == []

    edited_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/review-reports/{report['id']}",
        headers=admin_headers,
        json={
            "expected_version": 1,
            "summary": "人工补充后的周期总结",
            "next_actions": "下一轮验证新素材与人群组合",
        },
    )
    assert edited_response.status_code == 200, edited_response.text
    edited = edited_response.json()
    assert edited["version_no"] == 2
    stale = await api_client.patch(
        f"/api/v1/products/{product['id']}/review-reports/{report['id']}",
        headers=admin_headers,
        json={"expected_version": 1, "summary": "过期内容"},
    )
    assert stale.status_code == 409
    revisions = await api_client.get(
        f"/api/v1/products/{product['id']}/review-reports/{report['id']}/revisions",
        headers=viewer_headers,
    )
    assert revisions.status_code == 200
    assert [item["version_no"] for item in revisions.json()] == [2, 1]
    assert db_session.scalar(select(func.count(ReviewReportRevision.id))) == 2

    diagnosis_response = await api_client.post(
        f"/api/v1/products/{product['id']}/diagnoses/generate",
        headers=admin_headers,
        json={"source_review_report_id": report["id"], "notes": "开启下一轮"},
    )
    assert diagnosis_response.status_code == 200, diagnosis_response.text
    diagnosis = diagnosis_response.json()
    assert diagnosis["source_review_report_id"] == report["id"]
    detail = await api_client.get(
        f"/api/v1/products/{product['id']}/review-reports/{report['id']}",
        headers=viewer_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["follow_up_diagnoses"][0]["id"] == diagnosis["id"]

    actions = set(db_session.scalars(select(AuditLog.action)).all())
    assert {
        "performance_record.create",
        "review_report.generate",
        "review_report.update",
        "diagnosis.generate",
    }.issubset(actions)
    assert (
        db_session.scalar(
            select(func.count(AiUsageLog.id)).where(AiUsageLog.scene == "review_report")
        )
        == 1
    )
