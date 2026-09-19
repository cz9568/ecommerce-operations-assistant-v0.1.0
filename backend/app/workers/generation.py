import logging
from datetime import UTC, datetime, timedelta
from time import sleep
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import Settings, get_settings
from backend.app.database import SessionLocal
from backend.app.integrations.media import MediaAdapter, MediaAdapterError, get_media_adapter
from backend.app.integrations.storage import (
    MediaDownloader,
    StorageAdapter,
    StorageError,
    get_storage_adapter,
)
from backend.app.models.entities import GenerationJob
from backend.app.services.assets import (
    PreparedAsset,
    cleanup_prepared_assets,
    persist_prepared_assets,
    prepare_generation_assets,
)
from backend.app.services.generation_jobs import add_job_event, transition_job

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class GenerationWorker:
    def __init__(
        self,
        *,
        worker_id: str,
        session_factory: sessionmaker[Session] = SessionLocal,
        adapter: MediaAdapter | None = None,
        storage: StorageAdapter | None = None,
        downloader: MediaDownloader | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.worker_id = worker_id[:100]
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.adapter = adapter or get_media_adapter(self.settings)
        self.storage = storage or get_storage_adapter(self.settings)
        self.downloader = downloader or MediaDownloader(self.settings)

    def scan_timeouts_and_recover_locks(self) -> tuple[int, int]:
        timed_out = 0
        recovered = 0
        now = _now()
        timeout_cutoff = now - timedelta(seconds=self.settings.job_timeout_seconds)
        lock_cutoff = now - timedelta(seconds=self.settings.job_lock_timeout_seconds)
        with self.session_factory() as session:
            timeout_jobs = session.scalars(
                select(GenerationJob)
                .where(
                    GenerationJob.job_status == "running",
                    GenerationJob.started_at.is_not(None),
                    GenerationJob.started_at <= timeout_cutoff,
                )
                .with_for_update(skip_locked=True)
            ).all()
            for job in timeout_jobs:
                transition_job(
                    session,
                    job,
                    "timeout",
                    event_type="job.timeout",
                    message="生成任务超过最大运行时间",
                    data={"timeout_seconds": self.settings.job_timeout_seconds},
                )
                job.error_code = "GENERATION_JOB_TIMEOUT"
                job.error_message = "生成任务超过最大运行时间"
                job.locked_at = None
                job.locked_by = None
                job.heartbeat_at = now
                job.next_run_at = None
                timed_out += 1

            stale_jobs = session.scalars(
                select(GenerationJob)
                .where(
                    GenerationJob.job_status == "running",
                    GenerationJob.locked_at.is_not(None),
                    GenerationJob.locked_at <= lock_cutoff,
                    or_(
                        GenerationJob.started_at.is_(None),
                        GenerationJob.started_at > timeout_cutoff,
                    ),
                )
                .with_for_update(skip_locked=True)
            ).all()
            for job in stale_jobs:
                if job.external_job_id is None:
                    transition_job(
                        session,
                        job,
                        "pending",
                        event_type="job.lock_recovered",
                        message="Worker 锁已过期，任务重新排队",
                    )
                    job.next_run_at = now
                else:
                    job.version_no += 1
                    add_job_event(
                        session,
                        job,
                        "job.lock_recovered",
                        "Worker 锁已过期，保留外部任务并恢复轮询",
                        {"external_job_id": job.external_job_id},
                    )
                    job.next_run_at = now
                job.locked_at = None
                job.locked_by = None
                job.heartbeat_at = now
                recovered += 1
            session.commit()
        return timed_out, recovered

    def claim_next_job(self) -> int | None:
        now = _now()
        lock_cutoff = now - timedelta(seconds=self.settings.job_lock_timeout_seconds)
        with self.session_factory() as session:
            due = or_(GenerationJob.next_run_at.is_(None), GenerationJob.next_run_at <= now)
            claimable_status = or_(
                GenerationJob.job_status == "pending",
                and_(
                    GenerationJob.job_status == "running",
                    GenerationJob.external_job_id.is_not(None),
                ),
            )
            unlocked = or_(
                GenerationJob.locked_at.is_(None), GenerationJob.locked_at <= lock_cutoff
            )
            job = session.scalar(
                select(GenerationJob)
                .where(claimable_status, due, unlocked)
                .order_by(GenerationJob.next_run_at.asc(), GenerationJob.id.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.locked_by = self.worker_id
            job.locked_at = now
            job.heartbeat_at = now
            if job.job_status == "pending":
                transition_job(
                    session,
                    job,
                    "running",
                    event_type="job.claimed",
                    message="Worker 已领取生成任务",
                    data={"worker_id": self.worker_id},
                )
                job.progress_percent = max(job.progress_percent, 5)
            else:
                job.version_no += 1
                add_job_event(
                    session,
                    job,
                    "job.poll_claimed",
                    "Worker 已领取外部任务轮询",
                    {"worker_id": self.worker_id},
                )
            session.commit()
            return job.id

    def _release_for_poll(
        self,
        session: Session,
        job: GenerationJob,
        *,
        progress: int,
        message: str,
    ) -> None:
        job.progress_percent = max(job.progress_percent, min(progress, 99))
        job.next_run_at = _now() + timedelta(seconds=self.settings.job_poll_interval_seconds)
        job.locked_at = None
        job.locked_by = None
        job.heartbeat_at = _now()
        job.version_no += 1
        add_job_event(
            session,
            job,
            "provider.polling",
            message,
            {"progress_percent": job.progress_percent},
        )

    def _handle_submission_error(
        self, session: Session, job: GenerationJob, error: MediaAdapterError
    ) -> None:
        job.error_code = error.code
        job.error_message = error.message
        job.locked_at = None
        job.locked_by = None
        job.heartbeat_at = _now()
        if error.retryable and job.attempts < job.max_attempts:
            transition_job(
                session,
                job,
                "pending",
                event_type="job.retry_scheduled",
                message=error.message,
                data={"error_code": error.code, "attempts": job.attempts},
            )
            job.external_job_id = None
            job.next_run_at = _now() + timedelta(seconds=min(2**job.attempts, 60))
        else:
            transition_job(
                session,
                job,
                "failed",
                event_type="job.dead_lettered",
                message=error.message,
                data={"error_code": error.code, "attempts": job.attempts},
            )
            job.next_run_at = None

    def _handle_poll_error(
        self, session: Session, job: GenerationJob, error: MediaAdapterError
    ) -> None:
        job.error_code = error.code
        job.error_message = error.message
        job.locked_at = None
        job.locked_by = None
        job.heartbeat_at = _now()
        if error.retryable:
            job.next_run_at = _now() + timedelta(seconds=self.settings.job_poll_interval_seconds)
            job.version_no += 1
            add_job_event(
                session,
                job,
                "provider.poll_failed",
                error.message,
                {"error_code": error.code, "will_retry": True},
            )
        else:
            transition_job(
                session,
                job,
                "failed",
                event_type="job.dead_lettered",
                message=error.message,
                data={"error_code": error.code},
            )
            job.next_run_at = None

    def process_claimed_job(self, job_id: int) -> None:
        with self.session_factory() as session:
            job = session.scalar(
                select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
            )
            if job is None or job.job_status != "running" or job.locked_by != self.worker_id:
                return
            snapshot = dict(job.input_snapshot_json or {})
            kind = job.job_kind
            product_id = job.product_id
            provider_name = job.provider_name
            external_job_id = job.external_job_id
            if external_job_id is None:
                job.attempts += 1
                job.heartbeat_at = _now()
                job.version_no += 1
                add_job_event(
                    session,
                    job,
                    "provider.submitting",
                    "正在向媒体生成服务提交任务",
                    {"attempt": job.attempts},
                )
            session.commit()

        if external_job_id is None:
            try:
                submission = self.adapter.submit(kind=kind, input_snapshot=snapshot)
            except MediaAdapterError as error:
                with self.session_factory() as session:
                    job = session.scalar(
                        select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
                    )
                    if job is not None and job.job_status == "running":
                        self._handle_submission_error(session, job, error)
                        session.commit()
                return
            with self.session_factory() as session:
                job = session.scalar(
                    select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
                )
                if job is None or job.job_status != "running":
                    return
                job.external_job_id = submission.external_job_id
                job.provider_name = submission.provider_name
                job.progress_percent = max(job.progress_percent, 15)
                job.next_run_at = (
                    _now()
                    if submission.provider_name == "mock"
                    else _now() + timedelta(seconds=self.settings.job_poll_interval_seconds)
                )
                job.locked_at = None
                job.locked_by = None
                job.heartbeat_at = _now()
                job.error_code = None
                job.error_message = None
                job.version_no += 1
                add_job_event(
                    session,
                    job,
                    "provider.submitted",
                    "媒体生成服务已接受任务",
                    {
                        "provider_name": submission.provider_name,
                        "external_job_id": submission.external_job_id,
                    },
                )
                session.commit()
            return

        try:
            poll_result = self.adapter.poll(
                kind=kind,
                external_job_id=external_job_id,
                input_snapshot=snapshot,
            )
        except MediaAdapterError as error:
            with self.session_factory() as session:
                job = session.scalar(
                    select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
                )
                if job is not None and job.job_status == "running":
                    self._handle_poll_error(session, job, error)
                    session.commit()
                return

        prepared_assets: list[PreparedAsset] = []
        if poll_result.status == "succeeded" and poll_result.result:
            try:
                prepared_assets = prepare_generation_assets(
                    job_id=job_id,
                    product_id=product_id,
                    job_kind=kind,
                    provider_name=provider_name,
                    result=poll_result.result,
                    storage=self.storage,
                    downloader=self.downloader,
                )
            except StorageError as error:
                with self.session_factory() as session:
                    job = session.scalar(
                        select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
                    )
                    if (
                        job is not None
                        and job.job_status == "running"
                        and job.locked_by == self.worker_id
                    ):
                        self._handle_poll_error(
                            session,
                            job,
                            MediaAdapterError(error.code, error.message, retryable=error.retryable),
                        )
                        session.commit()
                return

        with self.session_factory() as session:
            job = session.scalar(
                select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
            )
            if job is None or job.job_status != "running" or job.locked_by != self.worker_id:
                cleanup_prepared_assets(prepared_assets, self.storage)
                return
            if poll_result.status in {"pending", "running"}:
                self._release_for_poll(
                    session,
                    job,
                    progress=poll_result.progress_percent,
                    message="外部任务仍在处理中",
                )
            elif poll_result.status == "succeeded":
                if not poll_result.result or not poll_result.result.get("assets"):
                    self._handle_poll_error(
                        session,
                        job,
                        MediaAdapterError(
                            "MEDIA_RESULT_INVALID",
                            "媒体任务成功但结果为空",
                            retryable=False,
                        ),
                    )
                else:
                    try:
                        asset_records, created_count = persist_prepared_assets(
                            session,
                            job=job,
                            prepared=prepared_assets,
                        )
                    except Exception:
                        cleanup_prepared_assets(prepared_assets, self.storage)
                        raise
                    add_job_event(
                        session,
                        job,
                        "assets.synced",
                        "生成结果已转存到素材库",
                        {
                            "asset_count": len(asset_records),
                            "created_count": created_count,
                            "asset_ids": [asset.id for asset in asset_records],
                        },
                    )
                    transition_job(
                        session,
                        job,
                        "succeeded",
                        event_type="job.succeeded",
                        message="媒体生成完成",
                        data={"asset_count": len(poll_result.result["assets"])},
                    )
                    job.result_json = poll_result.result
                    job.error_code = None
                    job.error_message = None
                    job.next_run_at = None
                    job.locked_at = None
                    job.locked_by = None
                    job.heartbeat_at = _now()
            else:
                error = MediaAdapterError(
                    poll_result.error_code or "MEDIA_GENERATION_FAILED",
                    poll_result.error_message or "媒体生成失败",
                    retryable=poll_result.retryable,
                )
                self._handle_submission_error(session, job, error)
            session.commit()

    def run_once(self) -> bool:
        self.scan_timeouts_and_recover_locks()
        job_id = self.claim_next_job()
        if job_id is None:
            return False
        try:
            self.process_claimed_job(job_id)
        except Exception:
            logger.exception("generation_job_processing_crashed", extra={"job_id": job_id})
            with self.session_factory() as session:
                job = session.scalar(
                    select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
                )
                if job is not None and job.job_status == "running":
                    unexpected_error = MediaAdapterError(
                        "WORKER_UNEXPECTED_ERROR",
                        "Worker 处理任务时发生未预期错误",
                        retryable=True,
                    )
                    if job.external_job_id is None:
                        self._handle_submission_error(session, job, unexpected_error)
                    else:
                        self._handle_poll_error(session, job, unexpected_error)
                    session.commit()
        return True

    def run_until_idle(self, *, max_jobs: int = 100) -> int:
        processed = 0
        while processed < max_jobs and self.run_once():
            processed += 1
        return processed

    def run_forever(self, stop_requested: Any) -> None:
        while not stop_requested.is_set():
            if not self.run_once():
                stop_requested.wait(self.settings.job_poll_interval_seconds)
            else:
                sleep(0)
