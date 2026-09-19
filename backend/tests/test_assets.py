from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import backend.app.integrations.storage.providers as storage_providers
from backend.app.config import Settings
from backend.app.integrations.media import MockMediaAdapter
from backend.app.integrations.storage import (
    LocalStorageAdapter,
    MediaDownloader,
    StorageError,
    mock_media_bytes,
)
from backend.app.models.entities import AuditLog, GeneratedAsset
from backend.app.workers import GenerationWorker
from backend.tests.conftest import TestSession
from backend.tests.test_generation_jobs import _prepare_selected_plans


def _settings(storage_path: Path) -> Settings:
    return Settings(
        database_password="test-password",
        jwt_secret="x" * 40,
        llm_api_key="test-key",
        generation_provider="mock",
        storage_local_path=storage_path,
        job_poll_interval_seconds=0,
        job_lock_timeout_seconds=1,
        job_timeout_seconds=60,
    )


async def test_asset_sync_query_review_content_and_idempotency(
    api_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    product, admin_headers, viewer_headers, main, video = await _prepare_selected_plans(
        api_client, db_session, monkeypatch
    )
    storage = LocalStorageAdapter(tmp_path / "assets")
    monkeypatch.setattr("backend.app.api.routes.assets.get_storage_adapter", lambda: storage)
    created_jobs: list[dict] = []
    for key, plan, extra in (
        ("asset-image-job", main, {"size": "1024x1024"}),
        ("asset-video-job", video, {"size": "1280*720", "duration_seconds": 5}),
    ):
        response = await api_client.post(
            f"/api/v1/products/{product['id']}/generation-jobs",
            headers=admin_headers,
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
        worker_id="asset-worker",
        session_factory=TestSession,
        adapter=MockMediaAdapter(),
        storage=storage,
        settings=_settings(tmp_path / "assets"),
    )
    assert worker.run_until_idle(max_jobs=10) == 4
    assert db_session.scalar(select(func.count(GeneratedAsset.id))) == 2

    listing = await api_client.get(
        f"/api/v1/products/{product['id']}/assets",
        headers=viewer_headers,
        params={"page": 1, "page_size": 20},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assets = listing.json()["items"]
    image_asset = next(asset for asset in assets if asset["asset_type"] == "image")
    video_asset = next(asset for asset in assets if asset["asset_type"] == "video")
    assert image_asset["review_status"] == "pending"
    assert image_asset["file_status"] == "available"
    assert image_asset["checksum_sha256"]
    assert image_asset["file_size_bytes"] > 0

    image_content = await api_client.get(image_asset["content_url"], headers=viewer_headers)
    video_content = await api_client.get(video_asset["content_url"], headers=viewer_headers)
    assert image_content.status_code == 200
    assert image_content.headers["content-type"].startswith("image/png")
    assert image_content.content.startswith(b"\x89PNG")
    assert video_content.status_code == 200
    assert video_content.headers["content-type"].startswith("video/mp4")

    viewer_update = await api_client.patch(
        f"/api/v1/products/{product['id']}/assets/{image_asset['id']}",
        headers=viewer_headers,
        json={"expected_lock_version": image_asset["lock_version"], "score": 5},
    )
    assert viewer_update.status_code == 403
    updated_response = await api_client.patch(
        f"/api/v1/products/{product['id']}/assets/{image_asset['id']}",
        headers=admin_headers,
        json={
            "expected_lock_version": image_asset["lock_version"],
            "usage_scene": "商品首图",
            "score": 4.5,
            "tags": ["清爽", "转化", "清爽"],
            "remark": "首轮候选",
        },
    )
    assert updated_response.status_code == 200, updated_response.text
    updated = updated_response.json()
    assert updated["tags"] == ["清爽", "转化"]
    assert float(updated["score"]) == 4.5
    stale_update = await api_client.patch(
        f"/api/v1/products/{product['id']}/assets/{image_asset['id']}",
        headers=admin_headers,
        json={"expected_lock_version": image_asset["lock_version"], "score": 3},
    )
    assert stale_update.status_code == 409
    assert stale_update.json()["code"] == "ASSET_VERSION_CONFLICT"

    review_response = await api_client.post(
        f"/api/v1/products/{product['id']}/assets/{image_asset['id']}/review",
        headers=admin_headers,
        json={
            "expected_lock_version": updated["lock_version"],
            "review_status": "approved",
        },
    )
    assert review_response.status_code == 200, review_response.text
    reviewed = review_response.json()
    assert reviewed["review_status"] == "approved"
    assert reviewed["reviewed_by"] is not None

    storage.resolve_path(reviewed["storage_key"]).write_bytes(b"MZ-not-media")
    invalid_content = await api_client.get(reviewed["content_url"], headers=viewer_headers)
    assert invalid_content.status_code == 410
    invalid_detail = (
        await api_client.get(
            f"/api/v1/products/{product['id']}/assets/{reviewed['id']}",
            headers=viewer_headers,
        )
    ).json()
    assert invalid_detail["file_status"] == "invalid"

    resync = await api_client.post(
        f"/api/v1/products/{product['id']}/assets/sync/{created_jobs[0]['id']}",
        headers=admin_headers,
    )
    assert resync.status_code == 200, resync.text
    assert len(resync.json()) == 1
    assert resync.json()[0]["file_status"] == "available"
    assert db_session.scalar(select(func.count(GeneratedAsset.id))) == 2

    second_image_job = await api_client.post(
        f"/api/v1/products/{product['id']}/generation-jobs",
        headers=admin_headers,
        json={
            "creative_plan_id": main["id"],
            "creative_plan_version_no": main["version_no"],
            "idempotency_key": "asset-image-job-second-version",
            "size": "1024x1024",
        },
    )
    assert second_image_job.status_code == 201
    assert worker.run_until_idle(max_jobs=5) == 2
    image_listing = await api_client.get(
        f"/api/v1/products/{product['id']}/assets",
        headers=viewer_headers,
        params={"asset_type": "image", "page": 1, "page_size": 20},
    )
    assert image_listing.status_code == 200
    assert image_listing.json()["total"] == 2
    assert [item["version_no"] for item in image_listing.json()["items"]] == [2, 1]

    audit_actions = set(
        db_session.scalars(
            select(AuditLog.action).where(
                AuditLog.action.in_(["asset.update", "asset.review", "asset.sync"])
            )
        ).all()
    )
    assert audit_actions == {"asset.update", "asset.review", "asset.sync"}


def test_local_storage_and_downloader_reject_unsafe_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    storage = LocalStorageAdapter(tmp_path / "assets")
    try:
        storage.put_bytes("../escape.png", b"unsafe")
    except StorageError as exc:
        assert exc.code == "ASSET_STORAGE_KEY_INVALID"
    else:
        raise AssertionError("目录穿越存储 Key 应被拒绝")

    png = mock_media_bytes("image")

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "image/png", "content-length": str(len(png.content))}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_bytes(self):
            yield png.content

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def stream(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(storage_providers, "_validate_public_https_url", lambda _url: None)
    monkeypatch.setattr(storage_providers.httpx, "Client", FakeClient)
    downloaded = MediaDownloader(_settings(tmp_path / "assets")).download(
        "https://cdn.example.test/result.png", kind="image"
    )
    assert downloaded.mime_type == "image/png"

    class ExecutableResponse(FakeResponse):
        headers = {"content-type": "application/x-msdownload"}

        def iter_bytes(self):
            yield b"MZ-executable"

    monkeypatch.setattr(FakeClient, "stream", lambda *_args, **_kwargs: ExecutableResponse())
    try:
        MediaDownloader(_settings(tmp_path / "assets")).download(
            "https://cdn.example.test/payload.exe", kind="image"
        )
    except StorageError as exc:
        assert exc.code == "ASSET_FILE_TYPE_INVALID"
    else:
        raise AssertionError("可执行文件不应被素材下载器接受")
