from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.app.api.schemas.performance import (
    ReviewReportGenerateRequest,
    ReviewReportUpdate,
)
from backend.app.errors import AppError
from backend.app.integrations.ai import AiGenerationError, get_text_provider
from backend.app.integrations.ai.prompts import ReviewOutput, build_prompt
from backend.app.models.entities import (
    PerformanceRecord,
    ProductDiagnosis,
    ReviewReport,
    ReviewReportRevision,
    User,
)
from backend.app.services.ai_usage import add_ai_usage_log
from backend.app.services.audit import add_audit_log
from backend.app.services.performance import calculate_metrics
from backend.app.services.products import get_product_or_error
from backend.app.services.settings import configured_text_provider


def _now() -> datetime:
    return datetime.now(UTC)


def _follow_up_diagnoses(session: Session, report_id: int) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ProductDiagnosis)
        .where(ProductDiagnosis.source_review_report_id == report_id)
        .order_by(ProductDiagnosis.id.desc())
    ).all()
    return [
        {"id": item.id, "version_no": item.version_no, "created_at": item.created_at}
        for item in rows
    ]


def _response(session: Session, item: ReviewReport) -> dict[str, Any]:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "period_start": item.period_start,
        "period_end": item.period_end,
        "summary": item.summary_text or "",
        "core_insights": item.insights_json or [],
        "problem_assessment": item.problem_analysis_json or [],
        "next_actions": item.next_actions_json or [],
        "input_snapshot": item.input_snapshot_json or {},
        "provider_name": item.provider_name or "unknown",
        "model_name": item.model_name or "unknown",
        "prompt_version": item.prompt_version or "unknown",
        "schema_version": item.schema_version or "unknown",
        "generated_by": item.generated_by,
        "edited_by": item.edited_by,
        "edited_at": item.edited_at,
        "version_no": item.version_no,
        "follow_up_diagnoses": _follow_up_diagnoses(session, item.id),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def get_review_report_or_error(
    session: Session, *, product_id: int, report_id: int
) -> ReviewReport:
    get_product_or_error(session, product_id)
    item = session.scalar(
        select(ReviewReport).where(
            ReviewReport.id == report_id,
            ReviewReport.product_id == product_id,
        )
    )
    if item is None:
        raise AppError(404, "REVIEW_REPORT_NOT_FOUND", "复盘报告不存在或不属于该商品")
    return item


def list_review_reports(
    session: Session, *, product_id: int, page: int, page_size: int
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    total = (
        session.scalar(
            select(func.count(ReviewReport.id)).where(ReviewReport.product_id == product_id)
        )
        or 0
    )
    rows = session.scalars(
        select(ReviewReport)
        .where(ReviewReport.product_id == product_id)
        .order_by(ReviewReport.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_response(session, item) for item in rows], int(total)


def list_review_revisions(
    session: Session, *, product_id: int, report_id: int
) -> list[dict[str, Any]]:
    get_review_report_or_error(session, product_id=product_id, report_id=report_id)
    rows = session.scalars(
        select(ReviewReportRevision)
        .where(ReviewReportRevision.review_report_id == report_id)
        .order_by(ReviewReportRevision.version_no.desc())
    ).all()
    return [
        {
            "id": item.id,
            "review_report_id": item.review_report_id,
            "version_no": item.version_no,
            "summary": item.summary_text,
            "core_insights": item.insights_json,
            "problem_assessment": item.problem_analysis_json,
            "next_actions": item.next_actions_json,
            "changed_by": item.changed_by,
            "created_at": item.created_at,
        }
        for item in rows
    ]


def _snapshot(
    session: Session,
    *,
    product_id: int,
    payload: ReviewReportGenerateRequest,
) -> dict[str, Any]:
    product = get_product_or_error(session, product_id)
    rows = session.scalars(
        select(PerformanceRecord)
        .where(
            PerformanceRecord.product_id == product_id,
            PerformanceRecord.record_status == "active",
            PerformanceRecord.period_start >= payload.period_start,
            PerformanceRecord.period_end <= payload.period_end,
        )
        .order_by(PerformanceRecord.period_start.asc(), PerformanceRecord.id.asc())
    ).all()
    if not rows:
        raise AppError(422, "REVIEW_NO_PERFORMANCE_DATA", "所选周期内没有可用于复盘的有效经营数据")
    impressions = sum(item.impressions for item in rows)
    clicks = sum(item.clicks for item in rows)
    conversions = sum(item.conversions for item in rows)
    spend = sum((item.spend for item in rows), Decimal("0"))
    revenue = sum((item.revenue for item in rows), Decimal("0"))
    ctr, conversion_rate, roi = calculate_metrics(
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        spend=spend,
        revenue=revenue,
    )
    return jsonable_encoder(
        {
            "product": {
                "id": product.id,
                "name": product.name,
                "platform": product.platform,
                "category": product.category,
                "price": product.price,
                "target_audience": product.target_audience,
                "selling_points": product.selling_points,
            },
            "period": {"start": payload.period_start, "end": payload.period_end},
            "aggregate": {
                "record_count": len(rows),
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "conversions": conversions,
                "conversion_rate": conversion_rate,
                "spend": spend,
                "revenue": revenue,
                "roi": roi,
            },
            "records": [
                {
                    "id": item.id,
                    "period_start": item.period_start,
                    "period_end": item.period_end,
                    "creative_plan_id": item.creative_plan_id,
                    "generated_asset_id": item.generated_asset_id,
                    "promotion_link_id": item.promotion_link_id,
                    "experiment_id": item.experiment_id,
                    "impressions": item.impressions,
                    "clicks": item.clicks,
                    "ctr": item.ctr,
                    "conversions": item.conversions,
                    "conversion_rate": item.conversion_rate,
                    "spend": item.spend,
                    "revenue": item.revenue,
                    "roi": item.roi,
                    "notes": item.notes,
                }
                for item in rows
            ],
            "operator_notes": payload.notes,
            "snapshot_at": _now(),
        }
    )


def generate_review_report(
    session: Session,
    *,
    product_id: int,
    payload: ReviewReportGenerateRequest,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    snapshot = _snapshot(session, product_id=product_id, payload=payload)
    prompt = build_prompt("review", snapshot)
    provider = configured_text_provider(get_text_provider, session)
    try:
        result = provider.generate_structured(prompt)
        output = ReviewOutput.model_validate(result.data)
    except AiGenerationError as exc:
        add_ai_usage_log(
            session,
            request_id=request_id,
            scene="review_report",
            provider_name=getattr(provider, "provider_name", "unknown"),
            model_name=getattr(provider, "model_name", "unknown"),
            prompt_version=prompt.prompt_version,
            status="failed",
            input_tokens=exc.usage.input_tokens,
            output_tokens=exc.usage.output_tokens,
            total_tokens=exc.usage.total_tokens,
            latency_ms=exc.latency_ms,
            attempts=exc.attempts,
            error_code=exc.code,
            actor_id=actor.id,
            target_type="product",
            target_id=str(product_id),
        )
        session.commit()
        raise AppError(
            429 if exc.code == "AI_RATE_LIMITED" else 502,
            exc.code,
            exc.message,
        ) from exc
    except ValidationError as exc:
        add_ai_usage_log(
            session,
            request_id=request_id,
            scene="review_report",
            provider_name=result.provider_name,
            model_name=result.model_name,
            prompt_version=prompt.prompt_version,
            status="failed",
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            total_tokens=result.usage.total_tokens,
            latency_ms=result.latency_ms,
            attempts=result.attempts,
            error_code="AI_OUTPUT_SCHEMA_INVALID",
            actor_id=actor.id,
            target_type="product",
            target_id=str(product_id),
        )
        session.commit()
        raise AppError(502, "AI_OUTPUT_SCHEMA_INVALID", "模型输出未通过复盘结构校验") from exc
    except Exception as exc:
        add_ai_usage_log(
            session,
            request_id=request_id,
            scene="review_report",
            provider_name=getattr(provider, "provider_name", "unknown"),
            model_name=getattr(provider, "model_name", "unknown"),
            prompt_version=prompt.prompt_version,
            status="failed",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            latency_ms=0,
            attempts=1,
            error_code="AI_GENERATION_FAILED",
            actor_id=actor.id,
            target_type="product",
            target_id=str(product_id),
        )
        session.commit()
        raise AppError(502, "AI_GENERATION_FAILED", "模型生成失败") from exc
    item = ReviewReport(
        product_id=product_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        summary_text=output.period_summary,
        insights_json=[output.core_insights],
        problem_analysis_json=[output.problem_assessment],
        next_actions_json=[output.next_actions],
        input_snapshot_json=snapshot,
        provider_name=result.provider_name,
        model_name=result.model_name,
        prompt_version=prompt.prompt_version,
        schema_version=prompt.schema_version,
        raw_output=result.raw_text,
        generated_by=actor.id,
        version_no=1,
    )
    session.add(item)
    session.flush()
    session.add(
        ReviewReportRevision(
            review_report_id=item.id,
            version_no=1,
            summary_text=item.summary_text,
            insights_json=item.insights_json,
            problem_analysis_json=item.problem_analysis_json,
            next_actions_json=item.next_actions_json,
            changed_by=actor.id,
        )
    )
    add_ai_usage_log(
        session,
        request_id=request_id,
        scene="review_report",
        provider_name=result.provider_name,
        model_name=result.model_name,
        prompt_version=prompt.prompt_version,
        status="succeeded",
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        total_tokens=result.usage.total_tokens,
        latency_ms=result.latency_ms,
        attempts=result.attempts,
        error_code=None,
        actor_id=actor.id,
        target_type="review_report",
        target_id=str(item.id),
    )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="review_report.generate",
        target_type="review_report",
        target_id=item.id,
        request_id=request_id,
        detail={
            "product_id": product_id,
            "period": [str(payload.period_start), str(payload.period_end)],
            "record_count": snapshot["aggregate"]["record_count"],
        },
    )
    session.commit()
    session.refresh(item)
    return _response(session, item)


def update_review_report(
    session: Session,
    *,
    product_id: int,
    report_id: int,
    payload: ReviewReportUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    item = get_review_report_or_error(session, product_id=product_id, report_id=report_id)
    source = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    mapping: dict[str, tuple[str, Any]] = {
        "summary": ("summary_text", lambda value: value),
        "core_insights": ("insights_json", lambda value: [value]),
        "problem_assessment": ("problem_analysis_json", lambda value: [value]),
        "next_actions": ("next_actions_json", lambda value: [value]),
    }
    values = {mapping[key][0]: mapping[key][1](value) for key, value in source.items()}
    result = session.execute(
        update(ReviewReport)
        .where(
            ReviewReport.id == item.id,
            ReviewReport.version_no == payload.expected_version,
        )
        .values(
            **values,
            edited_by=actor.id,
            edited_at=_now(),
            updated_at=_now(),
            version_no=ReviewReport.version_no + 1,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        current = get_review_report_or_error(session, product_id=product_id, report_id=report_id)
        raise AppError(
            409,
            "REVIEW_REPORT_VERSION_CONFLICT",
            "复盘报告已被其他操作更新，请刷新后重试",
            details={"current_version": current.version_no},
        )
    session.flush()
    updated_item = get_review_report_or_error(session, product_id=product_id, report_id=report_id)
    session.add(
        ReviewReportRevision(
            review_report_id=updated_item.id,
            version_no=updated_item.version_no,
            summary_text=updated_item.summary_text or "",
            insights_json=updated_item.insights_json or [],
            problem_analysis_json=updated_item.problem_analysis_json or [],
            next_actions_json=updated_item.next_actions_json or [],
            changed_by=actor.id,
        )
    )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="review_report.update",
        target_type="review_report",
        target_id=item.id,
        request_id=request_id,
        detail={"product_id": product_id, "changed_fields": sorted(source)},
    )
    session.commit()
    return _response(
        session,
        get_review_report_or_error(session, product_id=product_id, report_id=report_id),
    )
