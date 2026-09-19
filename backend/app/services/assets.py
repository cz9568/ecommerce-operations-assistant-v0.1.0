from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.schemas.assets import AssetReviewRequest, AssetUpdate
from backend.app.errors import AppError
from backend.app.integrations.storage import (
    MediaDownloader,
    StorageAdapter,
    StorageError,
    mock_media_bytes,
)
from backend.app.models.entities import CreativePlan, GeneratedAsset, GenerationJob, User
from backend.app.services.audit import add_audit_log
from backend.app.services.generation_jobs import add_job_event
from backend.app.services.products import get_product_or_error


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class PreparedAsset:
    source_asset_index: int
    storage_key: str
    mime_type: str
    file_size_bytes: int
    checksum_sha256: str
    model_name: str | None
    width: int | None
    height: int | None
    duration_sec: Decimal | None
    created_new_file: bool


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return parsed if parsed and parsed > 0 else None


def prepare_generation_assets(
    *,
    job_id: int,
    product_id: int,
    job_kind: str,
    provider_name: str | None,
    result: dict[str, Any],
    storage: StorageAdapter,
    downloader: MediaDownloader,
) -> list[PreparedAsset]:
    source_assets = result.get("assets")
    if not isinstance(source_assets, list) or not source_assets or len(source_assets) > 10:
        raise StorageError("ASSET_RESULT_INVALID", "生成结果中的素材数量无效")
    prepared: list[PreparedAsset] = []
    try:
        for index, source in enumerate(source_assets):
            if not isinstance(source, dict):
                raise StorageError("ASSET_RESULT_INVALID", "生成结果素材结构无效")
            source_url = source.get("url")
            if provider_name == "mock":
                downloaded = mock_media_bytes(job_kind)
            elif not isinstance(source_url, str) or not source_url:
                raise StorageError("ASSET_SOURCE_URL_MISSING", "生成结果缺少素材地址")
            else:
                downloaded = downloader.download(source_url, kind=job_kind)
            checksum = sha256(downloaded.content).hexdigest()
            storage_key = (
                f"products/{product_id}/{job_kind}/{job_id}/"
                f"{index}-{checksum[:16]}.{downloaded.extension}"
            )
            _path, created_new = storage.put_bytes(storage_key, downloaded.content)
            width = _positive_int(source.get("width")) if job_kind == "image" else None
            height = _positive_int(source.get("height")) if job_kind == "image" else None
            if job_kind == "image" and (width is None or height is None):
                raise StorageError("ASSET_DIMENSIONS_INVALID", "图片素材缺少有效宽高")
            duration = None
            if job_kind == "video":
                try:
                    duration = Decimal(str(source.get("duration_seconds")))
                except (InvalidOperation, TypeError, ValueError) as exc:
                    raise StorageError("ASSET_DURATION_INVALID", "视频素材时长无效") from exc
                if not duration.is_finite() or duration <= 0:
                    raise StorageError("ASSET_DURATION_INVALID", "视频素材时长无效")
            prepared.append(
                PreparedAsset(
                    source_asset_index=index,
                    storage_key=storage_key,
                    mime_type=downloaded.mime_type,
                    file_size_bytes=len(downloaded.content),
                    checksum_sha256=checksum,
                    model_name=str(result.get("model_name") or "") or None,
                    width=width,
                    height=height,
                    duration_sec=duration,
                    created_new_file=created_new,
                )
            )
    except Exception:
        cleanup_prepared_assets(prepared, storage)
        raise
    return prepared


def cleanup_prepared_assets(prepared: list[PreparedAsset], storage: StorageAdapter) -> None:
    for asset in prepared:
        if asset.created_new_file:
            try:
                storage.delete(asset.storage_key)
            except StorageError:
                pass


def persist_prepared_assets(
    session: Session,
    *,
    job: GenerationJob,
    prepared: list[PreparedAsset],
) -> tuple[list[GeneratedAsset], int]:
    plan = session.scalar(
        select(CreativePlan).where(CreativePlan.id == job.creative_plan_id).with_for_update()
    )
    if plan is None or plan.product_id != job.product_id:
        raise StorageError("ASSET_PLAN_INVALID", "素材关联方案不存在或归属错误")
    existing = {
        asset.source_asset_index: asset
        for asset in session.scalars(
            select(GeneratedAsset).where(GeneratedAsset.generation_job_id == job.id)
        ).all()
    }
    next_version = (
        session.scalar(
            select(func.max(GeneratedAsset.version_no)).where(
                GeneratedAsset.creative_plan_id == job.creative_plan_id,
                GeneratedAsset.asset_type == job.job_kind,
            )
        )
        or 0
    ) + 1
    records: list[GeneratedAsset] = []
    created_count = 0
    synced_at = _now()
    for item in prepared:
        record = existing.get(item.source_asset_index)
        if record is None:
            record = GeneratedAsset(
                product_id=job.product_id,
                creative_plan_id=job.creative_plan_id,
                generation_job_id=job.id,
                source_asset_index=item.source_asset_index,
                asset_type=job.job_kind,
                storage_key=item.storage_key,
                asset_url=(f"/api/v1/products/{job.product_id}/assets/pending/content"),
                mime_type=item.mime_type,
                file_size_bytes=item.file_size_bytes,
                checksum_sha256=item.checksum_sha256,
                file_status="available",
                model_name=item.model_name,
                width=item.width,
                height=item.height,
                duration_sec=item.duration_sec,
                review_status="pending",
                version_no=next_version,
                lock_version=1,
                tags_json=[],
                synced_at=synced_at,
            )
            session.add(record)
            session.flush()
            record.asset_url = f"/api/v1/products/{job.product_id}/assets/{record.id}/content"
            next_version += 1
            created_count += 1
        else:
            if record.checksum_sha256 and record.checksum_sha256 != item.checksum_sha256:
                raise StorageError("ASSET_SYNC_CONFLICT", "相同结果序号对应的素材内容不一致")
            record.file_status = "available"
            record.synced_at = synced_at
        records.append(record)
    return records, created_count


def _asset_response(asset: GeneratedAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "product_id": asset.product_id,
        "creative_plan_id": asset.creative_plan_id,
        "generation_job_id": asset.generation_job_id,
        "source_asset_index": asset.source_asset_index,
        "asset_type": asset.asset_type,
        "storage_key": asset.storage_key,
        "content_url": f"/api/v1/products/{asset.product_id}/assets/{asset.id}/content",
        "mime_type": asset.mime_type,
        "file_size_bytes": asset.file_size_bytes,
        "checksum_sha256": asset.checksum_sha256,
        "file_status": asset.file_status,
        "model_name": asset.model_name,
        "width": asset.width,
        "height": asset.height,
        "duration_sec": asset.duration_sec,
        "review_status": asset.review_status,
        "reviewed_by": asset.reviewed_by,
        "reviewed_at": asset.reviewed_at,
        "version_no": asset.version_no,
        "lock_version": asset.lock_version,
        "usage_scene": asset.usage_scene,
        "score": asset.score,
        "tags": asset.tags_json or [],
        "remark": asset.remark,
        "synced_at": asset.synced_at,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }


def get_asset_or_error(
    session: Session, *, product_id: int, asset_id: int, for_update: bool = False
) -> GeneratedAsset:
    statement = select(GeneratedAsset).where(
        GeneratedAsset.id == asset_id,
        GeneratedAsset.product_id == product_id,
    )
    if for_update:
        statement = statement.with_for_update()
    asset = session.scalar(statement)
    if asset is None:
        raise AppError(404, "ASSET_NOT_FOUND", "素材不存在或不属于该商品")
    return asset


def list_assets(
    session: Session,
    *,
    product_id: int,
    asset_type: str | None,
    review_status: str | None,
    file_status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    filters = [GeneratedAsset.product_id == product_id]
    if asset_type:
        filters.append(GeneratedAsset.asset_type == asset_type)
    if review_status:
        filters.append(GeneratedAsset.review_status == review_status)
    if file_status:
        filters.append(GeneratedAsset.file_status == file_status)
    total = session.scalar(select(func.count(GeneratedAsset.id)).where(*filters)) or 0
    assets = session.scalars(
        select(GeneratedAsset)
        .where(*filters)
        .order_by(GeneratedAsset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_asset_response(asset) for asset in assets], int(total)


def get_asset(session: Session, *, product_id: int, asset_id: int) -> dict[str, Any]:
    return _asset_response(get_asset_or_error(session, product_id=product_id, asset_id=asset_id))


def _check_lock_version(asset: GeneratedAsset, expected: int) -> None:
    if asset.lock_version != expected:
        raise AppError(
            409,
            "ASSET_VERSION_CONFLICT",
            "素材信息已被其他用户修改，请刷新后重试",
            details={"current_lock_version": asset.lock_version},
        )


def update_asset(
    session: Session,
    *,
    product_id: int,
    asset_id: int,
    payload: AssetUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    asset = get_asset_or_error(session, product_id=product_id, asset_id=asset_id, for_update=True)
    _check_lock_version(asset, payload.expected_lock_version)
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_lock_version"})
    changed_fields = sorted(changes)
    if "tags" in changes:
        asset.tags_json = changes.pop("tags")
    for field, value in changes.items():
        setattr(asset, field, value)
    asset.lock_version += 1
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="asset.update",
        target_type="generated_asset",
        target_id=asset.id,
        request_id=request_id,
        detail={"product_id": product_id, "fields": changed_fields},
    )
    session.commit()
    session.refresh(asset)
    return _asset_response(asset)


def review_asset(
    session: Session,
    *,
    product_id: int,
    asset_id: int,
    payload: AssetReviewRequest,
    actor: User,
    request_id: str | None,
    storage: StorageAdapter | None = None,
) -> dict[str, Any]:
    asset = get_asset_or_error(session, product_id=product_id, asset_id=asset_id, for_update=True)
    _check_lock_version(asset, payload.expected_lock_version)
    if payload.review_status == "approved":
        detected_status = _detect_file_status(asset, storage) if storage else asset.file_status
        if detected_status != "available":
            if asset.file_status != detected_status:
                asset.file_status = detected_status
                asset.lock_version += 1
                session.commit()
            raise AppError(409, "ASSET_FILE_UNAVAILABLE", "文件不可用的素材不能审核通过")
    previous_status = asset.review_status
    asset.review_status = payload.review_status
    asset.remark = payload.remark if payload.remark is not None else asset.remark
    asset.reviewed_by = actor.id if payload.review_status != "pending" else None
    asset.reviewed_at = _now() if payload.review_status != "pending" else None
    asset.lock_version += 1
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="asset.review",
        target_type="generated_asset",
        target_id=asset.id,
        request_id=request_id,
        detail={
            "product_id": product_id,
            "previous_status": previous_status,
            "review_status": payload.review_status,
        },
    )
    session.commit()
    session.refresh(asset)
    return _asset_response(asset)


def check_asset_file(
    session: Session,
    *,
    product_id: int,
    asset_id: int,
    storage: StorageAdapter,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    asset = get_asset_or_error(session, product_id=product_id, asset_id=asset_id, for_update=True)
    new_status = _detect_file_status(asset, storage)
    if asset.file_status != new_status:
        asset.file_status = new_status
        asset.lock_version += 1
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="asset.file_check",
        target_type="generated_asset",
        target_id=asset.id,
        request_id=request_id,
        detail={"product_id": product_id, "file_status": new_status},
    )
    session.commit()
    session.refresh(asset)
    return _asset_response(asset)


def _detect_file_status(asset: GeneratedAsset, storage: StorageAdapter) -> str:
    if not storage.exists(asset.storage_key):
        return "missing"
    try:
        content = storage.resolve_path(asset.storage_key).read_bytes()
    except OSError:
        return "missing"
    if asset.checksum_sha256 and sha256(content).hexdigest() != asset.checksum_sha256:
        return "invalid"
    return "available"


def get_asset_content_path(
    session: Session,
    *,
    product_id: int,
    asset_id: int,
    storage: StorageAdapter,
) -> tuple[str, str, str]:
    asset = get_asset_or_error(session, product_id=product_id, asset_id=asset_id, for_update=True)
    detected_status = _detect_file_status(asset, storage)
    if detected_status != "available":
        if asset.file_status != detected_status:
            asset.file_status = detected_status
            asset.lock_version += 1
            session.commit()
        raise AppError(410, "ASSET_FILE_UNAVAILABLE", "素材文件已失效、损坏或不存在")
    if asset.file_status != "available":
        asset.file_status = "available"
        asset.lock_version += 1
        session.commit()
    path = storage.resolve_path(asset.storage_key)
    extension = path.suffix or (".png" if asset.asset_type == "image" else ".mp4")
    return str(path), asset.mime_type or "application/octet-stream", f"asset-{asset.id}{extension}"


def sync_succeeded_job_assets(
    session: Session,
    *,
    product_id: int,
    job_id: int,
    storage: StorageAdapter,
    downloader: MediaDownloader,
    actor: User,
    request_id: str | None,
) -> list[dict[str, Any]]:
    job = session.scalar(
        select(GenerationJob).where(
            GenerationJob.id == job_id,
            GenerationJob.product_id == product_id,
        )
    )
    if job is None:
        raise AppError(404, "GENERATION_JOB_NOT_FOUND", "生成任务不存在或不属于该商品")
    if job.job_status != "succeeded" or not job.result_json:
        raise AppError(409, "ASSET_JOB_NOT_SYNCABLE", "只有已有结果的成功任务可以同步素材")
    prepared: list[PreparedAsset] = []
    try:
        prepared = prepare_generation_assets(
            job_id=job.id,
            product_id=job.product_id,
            job_kind=job.job_kind,
            provider_name=job.provider_name,
            result=job.result_json,
            storage=storage,
            downloader=downloader,
        )
        records, created_count = persist_prepared_assets(session, job=job, prepared=prepared)
    except StorageError as exc:
        cleanup_prepared_assets(prepared, storage)
        raise AppError(422 if not exc.retryable else 503, exc.code, exc.message) from exc
    except Exception:
        cleanup_prepared_assets(prepared, storage)
        raise
    if created_count:
        add_job_event(
            session,
            job,
            "assets.synced",
            "生成结果已转存到素材库",
            {"asset_count": created_count, "operator_user_id": actor.id},
        )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="asset.sync",
        target_type="generation_job",
        target_id=job.id,
        request_id=request_id,
        detail={"product_id": product_id, "created_count": created_count},
    )
    session.commit()
    return [_asset_response(record) for record in records]
