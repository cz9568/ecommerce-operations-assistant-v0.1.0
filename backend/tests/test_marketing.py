import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.integrations.ai import MockTextProvider
from backend.app.models.entities import (
    AuditLog,
    CreativePlan,
    GeneratedAsset,
    PromotionLinkClick,
)
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_product, _create_store


async def _marketing_context(
    client: httpx.AsyncClient, session: Session
) -> tuple[dict, dict[str, str], dict[str, str], int]:
    create_test_user(session, username="admin", password=ADMIN_PASSWORD, role="admin")
    create_test_user(session, username="viewer", password=VIEWER_PASSWORD, role="viewer")
    admin_headers = {"Authorization": f"Bearer {await login(client, 'admin', ADMIN_PASSWORD)}"}
    viewer_headers = {"Authorization": f"Bearer {await login(client, 'viewer', VIEWER_PASSWORD)}"}
    store = await _create_store(
        client,
        admin_headers,
        name="投放测试店",
        external_id="marketing-store-1",
    )
    product = await _create_product(
        client,
        admin_headers,
        store_id=store["id"],
        name="投放测试商品",
    )
    plan = CreativePlan(
        product_id=product["id"],
        plan_type="main_image",
        title="已选主图",
        content_json={"title": "已选主图"},
        status="selected",
        version_no=1,
    )
    session.add(plan)
    session.flush()
    asset = GeneratedAsset(
        product_id=product["id"],
        creative_plan_id=plan.id,
        source_asset_index=0,
        asset_type="image",
        storage_key="products/test/approved.png",
        file_size_bytes=100,
        file_status="available",
        review_status="approved",
        version_no=1,
        lock_version=1,
        tags_json=["主图"],
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return product, admin_headers, viewer_headers, asset.id


async def test_promotion_link_lifecycle_redirect_filter_and_statistics(
    api_client: httpx.AsyncClient,
    db_session: Session,
) -> None:
    product, admin_headers, viewer_headers, _asset_id = await _marketing_context(
        api_client, db_session
    )
    suggestion_response = await api_client.post(
        f"/api/v1/products/{product['id']}/promotion-links/generate",
        headers=admin_headers,
        json={},
    )
    assert suggestion_response.status_code == 200, suggestion_response.text
    suggestion = suggestion_response.json()["suggestions"][0]
    assert suggestion["utm"]["utm_campaign"] == f"product_{product['id']}"

    viewer_create = await api_client.post(
        f"/api/v1/products/{product['id']}/promotion-links",
        headers=viewer_headers,
        json=suggestion,
    )
    assert viewer_create.status_code == 403
    unsafe = await api_client.post(
        f"/api/v1/products/{product['id']}/promotion-links",
        headers=admin_headers,
        json={"link_name": "内网", "target_url": "http://127.0.0.1/admin"},
    )
    assert unsafe.status_code == 422
    assert unsafe.json()["code"] == "PROMOTION_TARGET_URL_UNSAFE"

    created_response = await api_client.post(
        f"/api/v1/products/{product['id']}/promotion-links",
        headers=admin_headers,
        json=suggestion,
    )
    assert created_response.status_code == 201, created_response.text
    link = created_response.json()
    assert len(link["tracking_code"]) >= 20

    first_click = await api_client.get(link["redirect_path"], headers={"user-agent": "Mozilla/5.0"})
    second_click = await api_client.get(
        link["redirect_path"], headers={"user-agent": "Mozilla/5.0"}
    )
    bot_click = await api_client.get(
        link["redirect_path"], headers={"user-agent": "ExampleBot/1.0"}
    )
    assert first_click.status_code == 307
    assert "utm_source=content" in first_click.headers["location"]
    assert second_click.status_code == 307
    assert bot_click.status_code == 307

    listing = await api_client.get(
        f"/api/v1/products/{product['id']}/promotion-links",
        headers=viewer_headers,
    )
    assert listing.status_code == 200
    assert listing.json()["items"][0]["click_count"] == 1
    stats = await api_client.get(
        f"/api/v1/products/{product['id']}/promotion-links/{link['id']}/statistics",
        headers=viewer_headers,
    )
    assert stats.status_code == 200
    assert stats.json()["counted_clicks"] == 1
    assert stats.json()["filtered_clicks"] == 2
    assert db_session.scalar(select(func.count(PromotionLinkClick.id))) == 3

    stopped = await api_client.patch(
        f"/api/v1/products/{product['id']}/promotion-links/{link['id']}",
        headers=admin_headers,
        json={"expected_version": link["lock_version"], "status": "inactive"},
    )
    assert stopped.status_code == 200
    unavailable = await api_client.get(link["redirect_path"])
    assert unavailable.status_code == 404


async def test_recommendation_confirmation_and_experiment_state_machine(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
) -> None:
    product, admin_headers, viewer_headers, asset_id = await _marketing_context(
        api_client, db_session
    )
    link_response = await api_client.post(
        f"/api/v1/products/{product['id']}/promotion-links",
        headers=admin_headers,
        json={
            "link_name": "实验链接",
            "target_url": "https://example.com/landing",
            "utm": {"utm_source": "test", "utm_campaign": "m8"},
        },
    )
    link = link_response.json()
    monkeypatch.setattr("backend.app.services.marketing.get_text_provider", MockTextProvider)

    generated_response = await api_client.post(
        f"/api/v1/products/{product['id']}/ad-recommendations/generate",
        headers=admin_headers,
        json={"asset_ids": [asset_id], "link_ids": [link["id"]]},
    )
    assert generated_response.status_code == 200, generated_response.text
    recommendation = generated_response.json()
    assert recommendation["confirm_status"] == "pending"
    assert recommendation["input_snapshot"]["approved_assets"][0]["id"] == asset_id
    assert recommendation["provider_name"] == "mock"

    viewer_edit = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-recommendations/{recommendation['id']}",
        headers=viewer_headers,
        json={"expected_version": 1, "objective": "无权修改"},
    )
    assert viewer_edit.status_code == 403
    edited_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-recommendations/{recommendation['id']}",
        headers=admin_headers,
        json={
            "expected_version": recommendation["version_no"],
            "objective": "先验证已审核素材与目标人群的点击效率",
        },
    )
    assert edited_response.status_code == 200, edited_response.text
    recommendation = edited_response.json()
    assert recommendation["objective_text"].startswith("先验证")

    viewer_confirm = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-recommendations/{recommendation['id']}/confirmation",
        headers=viewer_headers,
        json={"expected_version": 1, "confirm_status": "confirmed"},
    )
    assert viewer_confirm.status_code == 403
    confirmed_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-recommendations/{recommendation['id']}/confirmation",
        headers=admin_headers,
        json={
            "expected_version": recommendation["version_no"],
            "confirm_status": "confirmed",
            "remark": "仅确认实验方案，不执行真实投放",
        },
    )
    assert confirmed_response.status_code == 200, confirmed_response.text
    confirmed = confirmed_response.json()
    assert confirmed["confirm_status"] == "confirmed"
    locked_edit = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-recommendations/{recommendation['id']}",
        headers=admin_headers,
        json={"expected_version": confirmed["version_no"], "objective": "终态修改"},
    )
    assert locked_edit.status_code == 409
    duplicate = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-recommendations/{recommendation['id']}/confirmation",
        headers=admin_headers,
        json={"expected_version": confirmed["version_no"], "confirm_status": "rejected"},
    )
    assert duplicate.status_code == 409

    experiment_response = await api_client.post(
        f"/api/v1/products/{product['id']}/ad-experiments/generate",
        headers=admin_headers,
        json={
            "recommendation_id": confirmed["id"],
            "related_asset_id": asset_id,
            "related_link_id": link["id"],
            "experiment_name": "首轮小预算实验",
            "budget_amount": "300.00",
        },
    )
    assert experiment_response.status_code == 201, experiment_response.text
    experiment = experiment_response.json()
    assert experiment["experiment_status"] == "draft"

    edited_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-experiments/{experiment['id']}",
        headers=admin_headers,
        json={
            "expected_version": experiment["version_no"],
            "hypothesis_text": "已审核素材会改善点击率",
            "experiment_status": "confirmed",
        },
    )
    assert edited_response.status_code == 200, edited_response.text
    confirmed_experiment = edited_response.json()
    locked_content = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-experiments/{experiment['id']}",
        headers=admin_headers,
        json={
            "expected_version": confirmed_experiment["version_no"],
            "budget_amount": "500.00",
        },
    )
    assert locked_content.status_code == 409
    illegal = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-experiments/{experiment['id']}",
        headers=admin_headers,
        json={
            "expected_version": confirmed_experiment["version_no"],
            "experiment_status": "finished",
        },
    )
    assert illegal.status_code == 409
    running = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-experiments/{experiment['id']}",
        headers=admin_headers,
        json={
            "expected_version": confirmed_experiment["version_no"],
            "experiment_status": "running",
        },
    )
    assert running.status_code == 200
    finished = await api_client.patch(
        f"/api/v1/products/{product['id']}/ad-experiments/{experiment['id']}",
        headers=admin_headers,
        json={
            "expected_version": running.json()["version_no"],
            "experiment_status": "finished",
        },
    )
    assert finished.status_code == 200

    actions = set(db_session.scalars(select(AuditLog.action)).all())
    assert {
        "promotion_link.create",
        "ad_recommendation.generate",
        "ad_recommendation.update",
        "ad_recommendation.confirmed",
        "ad_experiment.generate",
        "ad_experiment.update",
    }.issubset(actions)
