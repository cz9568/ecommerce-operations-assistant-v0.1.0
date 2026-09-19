from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.errors import AppError
from backend.app.integrations.ai import MockTextProvider
from backend.app.integrations.media import (
    MediaAdapterError,
    MediaPollResult,
    MediaSubmission,
    MockMediaAdapter,
)
from backend.app.models.entities import AuditLog, GenerationJob, GenerationJobEvent
from backend.app.services.generation_jobs import transition_job
from backend.app.workers import GenerationWorker
from backend.tests.conftest import TestSession
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_product, _create_store


def _worker_settings(storage_path: Path | None = None) -> Settings:
    return Settings(
        database_password="test-password",
        jwt_secret="x" * 40,
        llm_api_key="test-key",
        generation_provider="mock",
        job_poll_interval_seconds=0,
        job_lock_timeout_seconds=1,
        job_timeout_seconds=60,
        storage_local_path=storage_path or Path("storage"),
    )


async def _prepare_selected_plans(
    client: httpx.AsyncClient,
    session: Session,
    monkeypatch,
) -> tuple[dict, dict[str, str], dict[str, str], dict, dict]:
    create_test_user(session, username="admin", password=ADMIN_PASSWORD, role="admin")
    create_test_user(session, username="viewer", password=VIEWER_PASSWORD, role="viewer")
    admin_headers = {"Authorization": f"Bearer {await login(client, 'admin', ADMIN_PASSWORD)}"}
    viewer_headers = {"Authorization": f"Bearer {await login(client, 'viewer', VIEWER_PASSWORD)}"}
    store = await _create_store(
        client,
        admin_headers,
        name="生成任务测试店",
        external_id="generation-job-store",
    )
    product = await _create_product(
        client,
        admin_headers,
        store_id=store["id"],
        name="生成任务商品",
    )
    monkeypatch.setattr("backend.app.services.diagnoses.get_text_provider", MockTextProvider)
    monkeypatch.setattr("backend.app.services.creative_plans.get_text_provider", MockTextProvider)
    diagnosis = await client.post(
        f"/api/v1/products/{product['id']}/diagnoses/generate",
        headers=admin_headers,
        json={},
    )
    assert diagnosis.status_code == 200
    main_plans = (
        await client.post(
            f"/api/v1/products/{product['id']}/creative-plans/generate",
            headers=admin_headers,
            json={"plan_type": "main_image"},
        )
    ).json()
    video_plans = (
        await client.post(
            f"/api/v1/products/{product['id']}/creative-plans/generate",
            headers=admin_headers,
            json={"plan_type": "video_script"},
        )
    ).json()
    main = (
        await client.post(
            f"/api/v1/products/{product['id']}/creative-plans/{main_plans[0]['id']}/status",
            headers=admin_headers,
            json={"status": "selected", "expected_version": 1},
        )
    ).json()
    video = (
        await client.post(
            f"/api/v1/products/{product['id']}/creative-plans/{video_plans[0]['id']}/status",
            headers=admin_headers,
            json={"status": "selected", "expected_version": 1},
        )
    ).json()
    return product, admin_headers, viewer_headers, main, video


async def test_generation_job_creation_idempotency_permissions_and_queries(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
) -> None:
    product, admin_headers, viewer_headers, main, _video = await _prepare_selected_plans(
        api_client, db_session, monkeypatch
    )
    payload = {
        "creative_plan_id": main["id"],
        "creative_plan_version_no": main["version_no"],
        "idempotency_key": "image-request-0001",
        "size": "1024x1024",
    }
    forbidden = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs",
        headers=viewer_headers,
        json=payload,
    )
    assert forbidden.status_code == 403
    created_response = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs",
        headers=admin_headers,
        json=payload,
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    assert created["job_status"] == "pending"
    assert created["job_kind"] == "image"
    assert created["input_snapshot"]["plan"]["version_no"] == main["version_no"]

    duplicate_response = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs",
        headers=admin_headers,
        json=payload,
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["id"] == created["id"]
    assert db_session.scalar(select(func.count(GenerationJob.id))) == 1

    listing = await api_client.get(
        f"/api/v1/products/{product['id']}/generation-jobs",
        headers=viewer_headers,
        params={"job_kind": "image", "job_status": "pending"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    detail = await api_client.get(
        f"/api/v1/products/{product['id']}/generation-jobs/{created['id']}",
        headers=viewer_headers,
    )
    assert detail.status_code == 200
    events = await api_client.get(
        f"/api/v1/products/{product['id']}/generation-jobs/{created['id']}/events",
        headers=viewer_headers,
    )
    assert events.status_code == 200
    assert [event["event_type"] for event in events.json()] == ["job.created"]

    stale_version = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs",
        headers=admin_headers,
        json={**payload, "idempotency_key": "image-request-0002", "creative_plan_version_no": 1},
    )
    assert stale_version.status_code == 409
    assert stale_version.json()["code"] == "CREATIVE_PLAN_VERSION_CONFLICT"


async def test_mock_worker_completes_image_and_video_without_duplicate_results(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    product, headers, _viewer_headers, main, video = await _prepare_selected_plans(
        api_client, db_session, monkeypatch
    )
    created_jobs = []
    for key, plan, extra in (
        ("mock-image-job", main, {"size": "1024x1024"}),
        ("mock-video-job", video, {"size": "1280*720", "duration_seconds": 5}),
    ):
        response = await api_client.post(
            f"/api/v1/products/{product['id']}/generation-jobs",
            headers=headers,
            json={
                "creative_plan_id": plan["id"],
                "creative_plan_version_no": plan["version_no"],
                "idempotency_key": key,
                **extra,
            },
        )
        assert response.status_code == 201, response.text
        created_jobs.append(response.json())

    worker = GenerationWorker(
        worker_id="test-worker",
        session_factory=TestSession,
        adapter=MockMediaAdapter(),
        settings=_worker_settings(tmp_path / "assets"),
    )
    assert worker.run_until_idle(max_jobs=10) == 4
    assert worker.run_until_idle(max_jobs=10) == 0

    jobs = db_session.scalars(select(GenerationJob).order_by(GenerationJob.id)).all()
    assert [job.job_status for job in jobs] == ["succeeded", "succeeded"]
    assert jobs[0].result_json["assets"][0]["url"].endswith(".png")
    assert jobs[1].result_json["assets"][0]["url"].endswith(".mp4")
    assert all(job.attempts == 1 and job.progress_percent == 100 for job in jobs)
    for created in created_jobs:
        event_types = db_session.scalars(
            select(GenerationJobEvent.event_type)
            .where(GenerationJobEvent.job_id == created["id"])
            .order_by(GenerationJobEvent.id)
        ).all()
        assert event_types == [
            "job.created",
            "job.claimed",
            "provider.submitting",
            "provider.submitted",
            "job.poll_claimed",
            "assets.synced",
            "job.succeeded",
        ]
    succeeded_cancel = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs/{jobs[0].id}/cancel",
        headers=headers,
        json={"expected_version": jobs[0].version_no},
    )
    assert succeeded_cancel.status_code == 409
    assert succeeded_cancel.json()["code"] == "GENERATION_JOB_NOT_CANCELLABLE"


async def test_manual_cancel_retry_limits_permissions_and_worker_race(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
) -> None:
    product, admin_headers, viewer_headers, main, _video = await _prepare_selected_plans(
        api_client, db_session, monkeypatch
    )
    created = (
        await api_client.post(
            f"/api/v1/products/{product['id']}/generation-jobs",
            headers=admin_headers,
            json={
                "creative_plan_id": main["id"],
                "creative_plan_version_no": main["version_no"],
                "idempotency_key": "cancel-race-image-job",
            },
        )
    ).json()

    class MustNotSubmitAdapter:
        provider_name = "test"

        def __init__(self) -> None:
            self.submit_calls = 0

        def submit(self, *, kind, input_snapshot):
            del kind, input_snapshot
            self.submit_calls += 1
            raise AssertionError("已取消任务不应提交到生成服务")

        def poll(self, *, kind, external_job_id, input_snapshot):
            raise AssertionError((kind, external_job_id, input_snapshot))

    adapter = MustNotSubmitAdapter()
    worker = GenerationWorker(
        worker_id="cancel-race-worker",
        session_factory=TestSession,
        adapter=adapter,
        settings=_worker_settings(),
    )
    assert worker.claim_next_job() == created["id"]
    running = (
        await api_client.get(
            f"/api/v1/products/{product['id']}/generation-jobs/{created['id']}",
            headers=admin_headers,
        )
    ).json()

    forbidden = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs/{created['id']}/cancel",
        headers=viewer_headers,
        json={"expected_version": running["version_no"]},
    )
    assert forbidden.status_code == 403
    stale = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs/{created['id']}/cancel",
        headers=admin_headers,
        json={"expected_version": running["version_no"] - 1},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "GENERATION_JOB_VERSION_CONFLICT"
    cancelled_response = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs/{created['id']}/cancel",
        headers=admin_headers,
        json={"expected_version": running["version_no"], "reason": "测试取消竞争"},
    )
    assert cancelled_response.status_code == 200
    cancelled = cancelled_response.json()
    assert cancelled["job_status"] == "cancelled"
    assert cancelled["cancelled_at"] is not None
    assert cancelled["cancelled_by"] is not None
    worker.process_claimed_job(created["id"])
    assert adapter.submit_calls == 0

    cancelled_again = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs/{created['id']}/cancel",
        headers=admin_headers,
        json={"expected_version": cancelled["version_no"]},
    )
    assert cancelled_again.status_code == 409
    assert cancelled_again.json()["code"] == "GENERATION_JOB_NOT_CANCELLABLE"

    failed_job = GenerationJob(
        product_id=product["id"],
        creative_plan_id=main["id"],
        creative_plan_version_no=main["version_no"],
        job_kind="image",
        job_status="failed",
        idempotency_key="manual-retry-image-job",
        input_snapshot_json={"plan": {"content": {}}, "parameters": {}},
        provider_name="test",
        external_job_id="failed-external-id",
        attempts=1,
        max_attempts=3,
        progress_percent=40,
        error_code="MEDIA_FAILED",
        error_message="上游失败",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        version_no=1,
    )
    exhausted_job = GenerationJob(
        product_id=product["id"],
        creative_plan_id=main["id"],
        creative_plan_version_no=main["version_no"],
        job_kind="image",
        job_status="failed",
        idempotency_key="exhausted-image-job",
        input_snapshot_json={},
        attempts=3,
        max_attempts=3,
        progress_percent=20,
        version_no=1,
    )
    db_session.add_all([failed_job, exhausted_job])
    db_session.commit()

    retried_response = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs/{failed_job.id}/retry",
        headers=admin_headers,
        json={"expected_version": 1, "reason": "参数已确认，重新执行"},
    )
    assert retried_response.status_code == 200
    retried = retried_response.json()
    assert retried["job_status"] == "pending"
    assert retried["progress_percent"] == 0
    assert retried["external_job_id"] is None
    assert retried["error_code"] is None
    assert retried["started_at"] is None

    exhausted_response = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs/{exhausted_job.id}/retry",
        headers=admin_headers,
        json={"expected_version": 1},
    )
    assert exhausted_response.status_code == 409
    assert exhausted_response.json()["code"] == "GENERATION_JOB_RETRY_LIMIT_REACHED"

    db_session.expire_all()
    event_types = db_session.scalars(
        select(GenerationJobEvent.event_type)
        .where(GenerationJobEvent.job_id.in_([created["id"], failed_job.id]))
        .order_by(GenerationJobEvent.id)
    ).all()
    assert "job.cancelled" in event_types
    assert "job.manual_retry_scheduled" in event_types
    audit_actions = set(
        db_session.scalars(
            select(AuditLog.action).where(
                AuditLog.action.in_(["generation_job.cancel", "generation_job.retry"])
            )
        ).all()
    )
    assert audit_actions == {"generation_job.cancel", "generation_job.retry"}


async def test_worker_retry_dead_letter_timeout_and_transition_guard(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    product, headers, _viewer_headers, main, _video = await _prepare_selected_plans(
        api_client, db_session, monkeypatch
    )
    response = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs",
        headers=headers,
        json={
            "creative_plan_id": main["id"],
            "creative_plan_version_no": main["version_no"],
            "idempotency_key": "retry-image-job",
        },
    )
    job_id = response.json()["id"]

    class RetryThenSucceedAdapter:
        provider_name = "mock"

        def __init__(self) -> None:
            self.submissions = 0

        def submit(self, *, kind, input_snapshot):
            del kind, input_snapshot
            self.submissions += 1
            if self.submissions == 1:
                raise MediaAdapterError("TEMPORARY", "暂时失败", retryable=True)
            return MediaSubmission("external-ok", self.provider_name)

        def poll(self, *, kind, external_job_id, input_snapshot):
            del kind, external_job_id, input_snapshot
            return MediaPollResult(
                status="succeeded",
                progress_percent=100,
                result={
                    "assets": [
                        {
                            "url": "https://example.com/result.png",
                            "media_type": "image/png",
                            "width": 1024,
                            "height": 1024,
                        }
                    ]
                },
            )

    adapter = RetryThenSucceedAdapter()
    worker = GenerationWorker(
        worker_id="retry-worker",
        session_factory=TestSession,
        adapter=adapter,
        settings=_worker_settings(tmp_path / "assets"),
    )
    assert worker.run_once() is True
    db_session.expire_all()
    pending = db_session.get(GenerationJob, job_id)
    assert pending.job_status == "pending"
    assert pending.attempts == 1
    pending.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert worker.run_until_idle(max_jobs=5) == 2
    db_session.expire_all()
    succeeded = db_session.get(GenerationJob, job_id)
    assert succeeded.job_status == "succeeded"
    assert succeeded.attempts == 2
    try:
        transition_job(
            db_session,
            succeeded,
            "running",
            event_type="illegal",
        )
    except AppError as exc:
        assert exc.code == "GENERATION_JOB_INVALID_TRANSITION"
    else:
        raise AssertionError("终态任务不应允许重新进入 running")

    timeout_job = GenerationJob(
        product_id=product["id"],
        creative_plan_id=main["id"],
        creative_plan_version_no=main["version_no"],
        job_kind="image",
        job_status="running",
        idempotency_key="timeout-image-job",
        input_snapshot_json={},
        attempts=1,
        max_attempts=3,
        progress_percent=30,
        started_at=datetime.now(UTC) - timedelta(seconds=120),
        version_no=1,
    )
    db_session.add(timeout_job)
    db_session.commit()
    timed_out, _recovered = worker.scan_timeouts_and_recover_locks()
    assert timed_out == 1
    db_session.expire_all()
    assert db_session.get(GenerationJob, timeout_job.id).job_status == "timeout"

    unexpected_job = GenerationJob(
        product_id=product["id"],
        creative_plan_id=main["id"],
        creative_plan_version_no=main["version_no"],
        job_kind="image",
        job_status="pending",
        idempotency_key="unexpected-image-job",
        input_snapshot_json={"plan": {"content": {}}, "parameters": {}},
        attempts=0,
        max_attempts=3,
        progress_percent=0,
        next_run_at=datetime.now(UTC),
        version_no=1,
    )
    db_session.add(unexpected_job)
    db_session.commit()

    class UnexpectedAdapter:
        provider_name = "test"

        def submit(self, *, kind, input_snapshot):
            del kind, input_snapshot
            raise RuntimeError("provider SDK crashed")

        def poll(self, *, kind, external_job_id, input_snapshot):
            raise AssertionError((kind, external_job_id, input_snapshot))

    crash_worker = GenerationWorker(
        worker_id="crash-worker",
        session_factory=TestSession,
        adapter=UnexpectedAdapter(),
        settings=_worker_settings(),
    )
    assert crash_worker.run_once() is True
    db_session.expire_all()
    recovered_job = db_session.get(GenerationJob, unexpected_job.id)
    assert recovered_job.job_status == "pending"
    assert recovered_job.error_code == "WORKER_UNEXPECTED_ERROR"
