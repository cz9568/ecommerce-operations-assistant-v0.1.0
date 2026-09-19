from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.schemas.generation_jobs import GenerationJobActionRequest, GenerationJobCreate
from backend.app.config import Settings
from backend.app.errors import AppError
from backend.app.models.entities import (
    CreativePlan,
    GenerationJob,
    GenerationJobEvent,
    User,
)
from backend.app.services.audit import add_audit_log
from backend.app.services.products import get_product_or_error
from backend.app.services.settings import resolve_runtime_settings

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "timeout"})
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled"}),
    "running": frozenset({"pending", "succeeded", "failed", "cancelled", "timeout"}),
    "succeeded": frozenset(),
    "failed": frozenset({"pending"}),
    "cancelled": frozenset(),
    "timeout": frozenset({"pending"}),
}


def _now() -> datetime:
    return datetime.now(UTC)


def add_job_event(
    session: Session,
    job: GenerationJob,
    event_type: str,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    session.add(
        GenerationJobEvent(
            job_id=job.id,
            event_type=event_type,
            event_message=message,
            event_data_json=data or {},
        )
    )


def transition_job(
    session: Session,
    job: GenerationJob,
    new_status: str,
    *,
    event_type: str,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    previous_status = job.job_status
    if new_status not in VALID_TRANSITIONS.get(previous_status, frozenset()):
        raise AppError(
            409,
            "GENERATION_JOB_INVALID_TRANSITION",
            f"生成任务不能从 {previous_status} 转为 {new_status}",
            details={"current_status": previous_status, "target_status": new_status},
        )
    job.job_status = new_status
    job.version_no += 1
    if new_status == "running" and job.started_at is None:
        job.started_at = _now()
    if new_status in TERMINAL_STATUSES:
        job.finished_at = _now()
    if new_status == "succeeded":
        job.progress_percent = 100
    add_job_event(
        session,
        job,
        event_type,
        message,
        {
            "from_status": previous_status,
            "to_status": new_status,
            **(data or {}),
        },
    )


def _job_response(job: GenerationJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "product_id": job.product_id,
        "creative_plan_id": job.creative_plan_id,
        "creative_plan_version_no": job.creative_plan_version_no,
        "job_kind": job.job_kind,
        "job_status": job.job_status,
        "idempotency_key": job.idempotency_key,
        "provider_name": job.provider_name,
        "external_job_id": job.external_job_id,
        "input_snapshot": job.input_snapshot_json or {},
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "progress_percent": job.progress_percent,
        "next_run_at": job.next_run_at,
        "result": job.result_json,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "requested_by": job.requested_by,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "cancelled_at": job.cancelled_at,
        "cancelled_by": job.cancelled_by,
        "version_no": job.version_no,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _event_response(event: GenerationJobEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "job_id": event.job_id,
        "event_type": event.event_type,
        "event_message": event.event_message,
        "event_data": event.event_data_json or {},
        "created_at": event.created_at,
    }


def _validate_parameters(
    plan: CreativePlan, payload: GenerationJobCreate, settings: Settings
) -> dict[str, Any]:
    if plan.plan_type == "main_image":
        if payload.duration_seconds is not None:
            raise AppError(422, "MEDIA_PARAMETERS_INVALID", "图片任务不能设置视频时长")
        size = payload.size or settings.image_size
        normalized = size.lower().replace("*", "x")
        try:
            width, height = (int(part) for part in normalized.split("x", maxsplit=1))
        except (TypeError, ValueError) as exc:
            raise AppError(422, "MEDIA_PARAMETERS_INVALID", "图片尺寸格式应为宽x高") from exc
        if not (512 <= width <= 2048 and 512 <= height <= 2048):
            raise AppError(422, "MEDIA_PARAMETERS_INVALID", "图片宽高必须在 512～2048 之间")
        return {"size": f"{width}x{height}"}
    size = (payload.size or settings.video_size).replace("x", "*")
    allowed_sizes = {"1280*720", "720*1280", "1920*1080", "1080*1920"}
    if size not in allowed_sizes:
        raise AppError(422, "MEDIA_PARAMETERS_INVALID", "视频尺寸不在允许范围内")
    duration = payload.duration_seconds or settings.video_duration_seconds
    if duration not in {5, 10}:
        raise AppError(422, "MEDIA_PARAMETERS_INVALID", "wan2.6 视频时长仅支持 5 或 10 秒")
    return {"size": size, "duration_seconds": duration}


def create_generation_job(
    session: Session,
    *,
    product_id: int,
    payload: GenerationJobCreate,
    actor: User,
    request_id: str | None,
) -> tuple[dict[str, Any], bool]:
    get_product_or_error(session, product_id)
    existing = session.scalar(
        select(GenerationJob).where(GenerationJob.idempotency_key == payload.idempotency_key)
    )
    if existing is not None:
        if (
            existing.product_id != product_id
            or existing.creative_plan_id != payload.creative_plan_id
            or existing.creative_plan_version_no != payload.creative_plan_version_no
        ):
            raise AppError(
                409,
                "IDEMPOTENCY_KEY_CONFLICT",
                "幂等键已被其他生成请求使用",
            )
        return _job_response(existing), False
    plan = session.scalar(
        select(CreativePlan).where(
            CreativePlan.id == payload.creative_plan_id,
            CreativePlan.product_id == product_id,
        )
    )
    if plan is None:
        raise AppError(404, "CREATIVE_PLAN_NOT_FOUND", "创意方案不存在或不属于该商品")
    if plan.status != "selected":
        raise AppError(409, "CREATIVE_PLAN_NOT_SELECTED", "只有已选中的方案可以发起生成")
    if plan.version_no != payload.creative_plan_version_no:
        raise AppError(
            409,
            "CREATIVE_PLAN_VERSION_CONFLICT",
            "方案版本已变化，请刷新后重新发起生成",
            details={"current_version": plan.version_no},
        )
    kind = "image" if plan.plan_type == "main_image" else "video"
    settings = resolve_runtime_settings(session)
    parameters = _validate_parameters(plan, payload, settings)
    model_name = settings.image_model if kind == "image" else settings.video_model
    snapshot = {
        "product_id": product_id,
        "plan": {
            "id": plan.id,
            "version_no": plan.version_no,
            "plan_type": plan.plan_type,
            "title": plan.title,
            "content": plan.content_json,
            "prompt_version": plan.prompt_version,
            "schema_version": plan.schema_version,
        },
        "parameters": parameters,
        "model_name": model_name,
        "completion_strategy": "polling",
        "requested_at": _now().isoformat(),
    }
    job = GenerationJob(
        product_id=product_id,
        creative_plan_id=plan.id,
        creative_plan_version_no=plan.version_no,
        job_kind=kind,
        job_status="pending",
        idempotency_key=payload.idempotency_key,
        input_snapshot_json=snapshot,
        requested_by=actor.id,
        attempts=0,
        max_attempts=settings.job_max_attempts,
        progress_percent=0,
        next_run_at=_now(),
        version_no=1,
    )
    session.add(job)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raced = session.scalar(
            select(GenerationJob).where(GenerationJob.idempotency_key == payload.idempotency_key)
        )
        if raced is not None:
            if (
                raced.product_id != product_id
                or raced.creative_plan_id != payload.creative_plan_id
                or raced.creative_plan_version_no != payload.creative_plan_version_no
            ):
                raise AppError(
                    409,
                    "IDEMPOTENCY_KEY_CONFLICT",
                    "幂等键已被其他生成请求使用",
                ) from exc
            return _job_response(raced), False
        raise AppError(409, "GENERATION_JOB_CREATE_CONFLICT", "生成任务创建冲突") from exc
    add_job_event(
        session,
        job,
        "job.created",
        "生成任务已创建，等待 Worker 领取",
        {"status": "pending", "plan_version_no": plan.version_no},
    )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="generation_job.create",
        target_type="generation_job",
        target_id=job.id,
        request_id=request_id,
        detail={
            "product_id": product_id,
            "creative_plan_id": plan.id,
            "creative_plan_version_no": plan.version_no,
            "job_kind": kind,
        },
    )
    session.commit()
    session.refresh(job)
    return _job_response(job), True


def get_job_or_error(
    session: Session, *, product_id: int, job_id: int, for_update: bool = False
) -> GenerationJob:
    get_product_or_error(session, product_id)
    statement = select(GenerationJob).where(
        GenerationJob.id == job_id,
        GenerationJob.product_id == product_id,
    )
    if for_update:
        statement = statement.with_for_update()
    job = session.scalar(statement)
    if job is None:
        raise AppError(404, "GENERATION_JOB_NOT_FOUND", "生成任务不存在或不属于该商品")
    return job


def list_generation_jobs(
    session: Session,
    *,
    product_id: int,
    job_kind: str | None,
    job_status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    filters = [GenerationJob.product_id == product_id]
    if job_kind:
        filters.append(GenerationJob.job_kind == job_kind)
    if job_status:
        filters.append(GenerationJob.job_status == job_status)
    total = session.scalar(select(func.count(GenerationJob.id)).where(*filters)) or 0
    jobs = session.scalars(
        select(GenerationJob)
        .where(*filters)
        .order_by(GenerationJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_job_response(job) for job in jobs], int(total)


def get_generation_job(session: Session, *, product_id: int, job_id: int) -> dict[str, Any]:
    return _job_response(get_job_or_error(session, product_id=product_id, job_id=job_id))


def list_generation_job_events(
    session: Session, *, product_id: int, job_id: int
) -> list[dict[str, Any]]:
    job = get_job_or_error(session, product_id=product_id, job_id=job_id)
    events = session.scalars(
        select(GenerationJobEvent)
        .where(GenerationJobEvent.job_id == job.id)
        .order_by(GenerationJobEvent.id.asc())
    ).all()
    return [_event_response(event) for event in events]


def _get_generation_job_for_update(
    session: Session,
    *,
    product_id: int,
    job_id: int,
) -> GenerationJob:
    job = session.scalar(
        select(GenerationJob)
        .where(GenerationJob.id == job_id, GenerationJob.product_id == product_id)
        .with_for_update()
    )
    if job is None:
        raise AppError(404, "GENERATION_JOB_NOT_FOUND", "生成任务不存在或不属于该商品")
    return job


def _check_action_version(job: GenerationJob, expected_version: int) -> None:
    if job.version_no != expected_version:
        raise AppError(
            409,
            "GENERATION_JOB_VERSION_CONFLICT",
            "任务状态已变化，请刷新后重试",
            details={"current_version": job.version_no, "current_status": job.job_status},
        )


def cancel_generation_job(
    session: Session,
    *,
    product_id: int,
    job_id: int,
    payload: GenerationJobActionRequest,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    job = _get_generation_job_for_update(session, product_id=product_id, job_id=job_id)
    _check_action_version(job, payload.expected_version)
    if job.job_status not in {"pending", "running"}:
        raise AppError(
            409,
            "GENERATION_JOB_NOT_CANCELLABLE",
            "只有等待中或运行中的任务可以取消",
            details={"current_status": job.job_status},
        )
    previous_status = job.job_status
    now = _now()
    transition_job(
        session,
        job,
        "cancelled",
        event_type="job.cancelled",
        message=payload.reason or "用户取消了生成任务",
        data={
            "operator_user_id": actor.id,
            "reason": payload.reason,
            "external_task_may_continue": previous_status == "running",
            "external_job_id_recorded": job.external_job_id is not None,
        },
    )
    job.cancelled_at = now
    job.cancelled_by = actor.id
    job.next_run_at = None
    job.locked_at = None
    job.locked_by = None
    job.heartbeat_at = now
    job.error_code = None
    job.error_message = None
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="generation_job.cancel",
        target_type="generation_job",
        target_id=job.id,
        request_id=request_id,
        detail={
            "product_id": product_id,
            "previous_status": previous_status,
            "reason": payload.reason,
        },
    )
    session.commit()
    session.refresh(job)
    return _job_response(job)


def retry_generation_job(
    session: Session,
    *,
    product_id: int,
    job_id: int,
    payload: GenerationJobActionRequest,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    job = _get_generation_job_for_update(session, product_id=product_id, job_id=job_id)
    _check_action_version(job, payload.expected_version)
    if job.job_status not in {"failed", "timeout"}:
        raise AppError(
            409,
            "GENERATION_JOB_NOT_RETRYABLE",
            "只有失败或超时的任务可以人工重试",
            details={"current_status": job.job_status},
        )
    if job.attempts >= job.max_attempts:
        raise AppError(
            409,
            "GENERATION_JOB_RETRY_LIMIT_REACHED",
            "任务已达到最大尝试次数，不能继续重试",
            details={"attempts": job.attempts, "max_attempts": job.max_attempts},
        )
    previous_status = job.job_status
    resume_external_task = previous_status == "timeout" and job.external_job_id is not None
    transition_job(
        session,
        job,
        "pending",
        event_type="job.manual_retry_scheduled",
        message=payload.reason or "用户发起人工重试",
        data={
            "operator_user_id": actor.id,
            "reason": payload.reason,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "resume_external_task": resume_external_task,
        },
    )
    now = _now()
    job.progress_percent = 15 if resume_external_task else 0
    job.next_run_at = now
    job.locked_at = None
    job.locked_by = None
    job.heartbeat_at = now
    job.result_json = None
    job.error_code = None
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    job.cancelled_at = None
    job.cancelled_by = None
    if not resume_external_task:
        job.external_job_id = None
        job.provider_name = None
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="generation_job.retry",
        target_type="generation_job",
        target_id=job.id,
        request_id=request_id,
        detail={
            "product_id": product_id,
            "previous_status": previous_status,
            "reason": payload.reason,
            "resume_external_task": resume_external_task,
        },
    )
    session.commit()
    session.refresh(job)
    return _job_response(job)
