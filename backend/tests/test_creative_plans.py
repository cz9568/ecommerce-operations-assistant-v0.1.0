import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.integrations.ai import AiGenerationError, MockTextProvider
from backend.app.models.entities import AiUsageLog, CreativePlan
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_product, _create_store


async def _prepare_product_with_diagnosis(
    client: httpx.AsyncClient,
    session: Session,
    monkeypatch,
) -> tuple[dict, dict[str, str], dict[str, str]]:
    create_test_user(session, username="admin", password=ADMIN_PASSWORD, role="admin")
    create_test_user(session, username="viewer", password=VIEWER_PASSWORD, role="viewer")
    admin_headers = {"Authorization": f"Bearer {await login(client, 'admin', ADMIN_PASSWORD)}"}
    viewer_headers = {"Authorization": f"Bearer {await login(client, 'viewer', VIEWER_PASSWORD)}"}
    store = await _create_store(
        client,
        admin_headers,
        name="创意方案测试店",
        external_id="creative-plan-store",
    )
    product = await _create_product(
        client,
        admin_headers,
        store_id=store["id"],
        name="创意方案商品",
    )
    monkeypatch.setattr("backend.app.services.diagnoses.get_text_provider", MockTextProvider)
    diagnosis = await client.post(
        f"/api/v1/products/{product['id']}/diagnoses/generate",
        headers=admin_headers,
        json={},
    )
    assert diagnosis.status_code == 200, diagnosis.text
    return product, admin_headers, viewer_headers


async def test_generate_main_image_and_video_plans_with_history(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
) -> None:
    product, admin_headers, viewer_headers = await _prepare_product_with_diagnosis(
        api_client, db_session, monkeypatch
    )
    monkeypatch.setattr("backend.app.services.creative_plans.get_text_provider", MockTextProvider)

    main_response = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/generate",
        headers=admin_headers,
        json={"plan_type": "main_image", "notes": "突出收纳场景"},
    )
    assert main_response.status_code == 201, main_response.text
    main_plans = main_response.json()
    assert len(main_plans) >= 3
    assert len({item["generation_batch_id"] for item in main_plans}) == 1
    for item in main_plans:
        assert item["status"] == "draft"
        assert item["version_no"] == 1
        assert {
            "title",
            "visual_concept",
            "composition",
            "copy_text",
            "generation_prompt",
            "rationale",
        } <= set(item["content"])

    video_response = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/generate",
        headers=admin_headers,
        json={"plan_type": "video_script"},
    )
    assert video_response.status_code == 201, video_response.text
    video_plans = video_response.json()
    assert len(video_plans) >= 3
    for item in video_plans:
        assert item["content"]["hook"]
        assert item["content"]["call_to_action"]
        assert item["content"]["scenes"][0]["visual"]
        assert item["content"]["scenes"][0]["voiceover"]

    listing = await api_client.get(
        f"/api/v1/products/{product['id']}/creative-plans",
        headers=viewer_headers,
        params={"plan_type": "main_image"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 3
    forbidden = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/generate",
        headers=viewer_headers,
        json={"plan_type": "main_image"},
    )
    assert forbidden.status_code == 403

    assert (
        db_session.scalar(select(func.count(AiUsageLog.id)).where(AiUsageLog.status == "succeeded"))
        == 3
    )


async def test_creative_plan_edit_selection_archive_and_revisions(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
) -> None:
    product, headers, _viewer_headers = await _prepare_product_with_diagnosis(
        api_client, db_session, monkeypatch
    )
    monkeypatch.setattr("backend.app.services.creative_plans.get_text_provider", MockTextProvider)
    generated = (
        await api_client.post(
            f"/api/v1/products/{product['id']}/creative-plans/generate",
            headers=headers,
            json={"plan_type": "main_image"},
        )
    ).json()
    first, second = generated[:2]
    edited_content = {
        **first["content"],
        "title": "编辑后的场景方向",
        "copy_text": "轻松收纳每一天",
    }
    edited_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/creative-plans/{first['id']}",
        headers=headers,
        json={"content": edited_content, "expected_version": 1},
    )
    assert edited_response.status_code == 200, edited_response.text
    edited = edited_response.json()
    assert edited["title"] == "编辑后的场景方向"
    assert edited["version_no"] == 2

    select_first = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/{first['id']}/status",
        headers=headers,
        json={"status": "selected", "expected_version": 2},
    )
    assert select_first.status_code == 200
    assert select_first.json()["version_no"] == 3
    reject_archive = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/{first['id']}/status",
        headers=headers,
        json={"status": "archived", "expected_version": 3},
    )
    assert reject_archive.status_code == 409
    assert reject_archive.json()["code"] == "SELECTED_PLAN_CANNOT_ARCHIVE"

    select_second = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/{second['id']}/status",
        headers=headers,
        json={"status": "selected", "expected_version": 1},
    )
    assert select_second.status_code == 200
    selected_count = db_session.scalar(
        select(func.count(CreativePlan.id)).where(
            CreativePlan.product_id == product["id"],
            CreativePlan.plan_type == "main_image",
            CreativePlan.status == "selected",
        )
    )
    assert selected_count == 1
    refreshed_first = (
        await api_client.get(
            f"/api/v1/products/{product['id']}/creative-plans/{first['id']}",
            headers=headers,
        )
    ).json()
    assert refreshed_first["status"] == "draft"
    assert refreshed_first["version_no"] == 4

    archive_first = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/{first['id']}/status",
        headers=headers,
        json={"status": "archived", "expected_version": 4},
    )
    assert archive_first.status_code == 200
    assert archive_first.json()["status"] == "archived"
    archived_edit = await api_client.patch(
        f"/api/v1/products/{product['id']}/creative-plans/{first['id']}",
        headers=headers,
        json={"content": edited_content, "expected_version": 5},
    )
    assert archived_edit.status_code == 409
    stale = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/{second['id']}/status",
        headers=headers,
        json={"status": "draft", "expected_version": 1},
    )
    assert stale.status_code == 409

    revisions = await api_client.get(
        f"/api/v1/products/{product['id']}/creative-plans/{first['id']}/revisions",
        headers=headers,
    )
    assert revisions.status_code == 200
    assert [item["version_no"] for item in revisions.json()] == [5, 4, 3, 2, 1]


async def test_creative_plan_requires_diagnosis_and_failed_ai_creates_no_plan(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
) -> None:
    create_test_user(db_session, username="admin", password=ADMIN_PASSWORD, role="admin")
    headers = {"Authorization": f"Bearer {await login(api_client, 'admin', ADMIN_PASSWORD)}"}
    store = await _create_store(
        api_client,
        headers,
        name="创意失败测试店",
        external_id="creative-plan-failed-store",
    )
    product = await _create_product(
        api_client,
        headers,
        store_id=store["id"],
        name="无诊断商品",
    )
    without_diagnosis = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/generate",
        headers=headers,
        json={"plan_type": "video_script"},
    )
    assert without_diagnosis.status_code == 409
    assert without_diagnosis.json()["code"] == "DIAGNOSIS_REQUIRED"

    monkeypatch.setattr("backend.app.services.diagnoses.get_text_provider", MockTextProvider)
    diagnosis = await api_client.post(
        f"/api/v1/products/{product['id']}/diagnoses/generate",
        headers=headers,
        json={},
    )
    assert diagnosis.status_code == 200

    class FailedProvider:
        provider_name = "test"
        model_name = "failed-creative-model"

        def generate_structured(self, _prompt):
            raise AiGenerationError("AI_NETWORK_ERROR", "模型网络异常", attempts=2)

    monkeypatch.setattr("backend.app.services.creative_plans.get_text_provider", FailedProvider)
    failed = await api_client.post(
        f"/api/v1/products/{product['id']}/creative-plans/generate",
        headers=headers,
        json={"plan_type": "video_script"},
    )
    assert failed.status_code == 502
    assert failed.json()["code"] == "AI_NETWORK_ERROR"
    assert db_session.scalar(select(func.count(CreativePlan.id))) == 0
    assert (
        db_session.scalar(select(func.count(AiUsageLog.id)).where(AiUsageLog.status == "failed"))
        == 1
    )
