from datetime import UTC, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.app.api.schemas.diagnoses import DiagnosisGenerateRequest, DiagnosisUpdate
from backend.app.errors import AppError
from backend.app.integrations.ai import AiGenerationError, get_text_provider
from backend.app.integrations.ai.prompts import DiagnosisOutput, build_prompt
from backend.app.models.entities import (
    Competitor,
    InventoryItem,
    Product,
    ProductDiagnosis,
    ProductSku,
    ReviewReport,
    User,
)
from backend.app.services.ai_usage import add_ai_usage_log
from backend.app.services.audit import add_audit_log
from backend.app.services.products import get_product_or_error
from backend.app.services.settings import configured_text_provider

DIAGNOSIS_FIELDS = (
    "positioning",
    "price_band",
    "audience_insights",
    "pain_points",
    "selling_point_analysis",
    "risks",
    "recommendations",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _diagnosis_response(diagnosis: ProductDiagnosis) -> dict[str, Any]:
    return {
        "id": diagnosis.id,
        "product_id": diagnosis.product_id,
        "source_type": diagnosis.source_type,
        "source_review_report_id": diagnosis.source_review_report_id,
        **{field: getattr(diagnosis, field) or "" for field in DIAGNOSIS_FIELDS},
        "input_snapshot": diagnosis.input_snapshot_json or {},
        "model_name": diagnosis.model_name or "unknown",
        "provider_name": diagnosis.provider_name or "unknown",
        "prompt_version": diagnosis.prompt_version or "unknown",
        "schema_version": diagnosis.schema_version or "unknown",
        "generated_by": diagnosis.generated_by,
        "edited_by": diagnosis.edited_by,
        "edited_at": diagnosis.edited_at,
        "version_no": diagnosis.version_no,
        "created_at": diagnosis.created_at,
        "updated_at": diagnosis.updated_at,
    }


def get_diagnosis_or_error(
    session: Session, *, product_id: int, diagnosis_id: int
) -> ProductDiagnosis:
    get_product_or_error(session, product_id)
    diagnosis = session.scalar(
        select(ProductDiagnosis).where(
            ProductDiagnosis.id == diagnosis_id,
            ProductDiagnosis.product_id == product_id,
        )
    )
    if diagnosis is None:
        raise AppError(404, "DIAGNOSIS_NOT_FOUND", "商品诊断不存在或不属于该商品")
    return diagnosis


def list_diagnoses(
    session: Session, *, product_id: int, page: int, page_size: int
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    total = (
        session.scalar(
            select(func.count(ProductDiagnosis.id)).where(ProductDiagnosis.product_id == product_id)
        )
        or 0
    )
    rows = session.scalars(
        select(ProductDiagnosis)
        .where(ProductDiagnosis.product_id == product_id)
        .order_by(ProductDiagnosis.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_diagnosis_response(row) for row in rows], int(total)


def get_diagnosis(session: Session, *, product_id: int, diagnosis_id: int) -> dict[str, Any]:
    return _diagnosis_response(
        get_diagnosis_or_error(session, product_id=product_id, diagnosis_id=diagnosis_id)
    )


def _input_snapshot(
    session: Session,
    *,
    product: Product,
    payload: DiagnosisGenerateRequest,
) -> tuple[dict[str, Any], list[str]]:
    competitors = session.scalars(
        select(Competitor)
        .where(Competitor.product_id == product.id, Competitor.status == "active")
        .order_by(Competitor.id.asc())
        .limit(20)
    ).all()
    inventory_rows = session.execute(
        select(ProductSku, InventoryItem)
        .outerjoin(InventoryItem, InventoryItem.sku_id == ProductSku.id)
        .where(ProductSku.product_id == product.id)
        .order_by(ProductSku.id.asc())
        .limit(50)
    ).all()
    source_review = None
    if payload.source_review_report_id is not None:
        source_review = session.scalar(
            select(ReviewReport).where(
                ReviewReport.id == payload.source_review_report_id,
                ReviewReport.product_id == product.id,
            )
        )
        if source_review is None:
            raise AppError(404, "REVIEW_REPORT_NOT_FOUND", "来源复盘不存在或不属于该商品")
    snapshot = {
        "product": {
            "id": product.id,
            "name": product.name,
            "platform": product.platform,
            "category": product.category,
            "price": product.price,
            "cost": product.cost,
            "target_audience": product.target_audience,
            "selling_points": product.selling_points,
            "product_url": product.product_url,
            "status": product.status,
        },
        "competitors": [
            {
                "id": item.id,
                "name": item.name,
                "platform": item.platform,
                "price": item.price,
                "sales_hint": item.sales_hint,
                "title": item.title,
                "selling_points": item.selling_points,
                "review_keywords": item.review_keywords,
                "field_sources": item.field_sources_json or {},
            }
            for item in competitors
        ],
        "sku_inventory": [
            {
                "sku_id": sku.id,
                "sku_code": sku.sku_code,
                "sku_name": sku.sku_name,
                "specs": sku.spec_json or {},
                "price": sku.price,
                "status": sku.status,
                "stock_qty": inventory.stock_qty if inventory else None,
                "locked_qty": inventory.locked_qty if inventory else None,
                "warning_threshold": inventory.warning_threshold if inventory else None,
            }
            for sku, inventory in inventory_rows
        ],
        "source_review": (
            {
                "id": source_review.id,
                "period_start": source_review.period_start,
                "period_end": source_review.period_end,
                "summary": source_review.summary_text,
                "insights": source_review.insights_json or [],
                "problems": source_review.problem_analysis_json or [],
                "next_actions": source_review.next_actions_json or [],
            }
            if source_review
            else None
        ),
        "operator_notes": payload.notes,
        "snapshot_at": _now(),
    }
    missing = []
    if not product.target_audience:
        missing.append("商品目标人群")
    if not product.selling_points:
        missing.append("商品卖点")
    if not competitors:
        missing.append("竞品数据")
    if not inventory_rows:
        missing.append("SKU 与库存数据")
    return jsonable_encoder(snapshot), missing


def generate_diagnosis(
    session: Session,
    *,
    product_id: int,
    payload: DiagnosisGenerateRequest,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    product = get_product_or_error(session, product_id)
    snapshot, missing = _input_snapshot(session, product=product, payload=payload)
    prompt = build_prompt("diagnosis", snapshot, missing_fields=missing)
    provider = configured_text_provider(get_text_provider, session)
    try:
        result = provider.generate_structured(prompt)
    except AiGenerationError as exc:
        add_ai_usage_log(
            session,
            request_id=request_id,
            scene="product_diagnosis",
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
            target_id=str(product.id),
        )
        session.commit()
        status_code = 429 if exc.code == "AI_RATE_LIMITED" else 502
        raise AppError(status_code, exc.code, exc.message) from exc
    except Exception as exc:
        add_ai_usage_log(
            session,
            request_id=request_id,
            scene="product_diagnosis",
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
            target_id=str(product.id),
        )
        session.commit()
        raise AppError(502, "AI_GENERATION_FAILED", "模型生成失败") from exc
    try:
        output = DiagnosisOutput.model_validate(result.data)
    except ValidationError as exc:
        add_ai_usage_log(
            session,
            request_id=request_id,
            scene="product_diagnosis",
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
            target_id=str(product.id),
        )
        session.commit()
        raise AppError(502, "AI_OUTPUT_SCHEMA_INVALID", "模型输出未通过诊断结构校验") from exc
    diagnosis = ProductDiagnosis(
        product_id=product.id,
        source_type="review" if payload.source_review_report_id else "ai",
        source_review_report_id=payload.source_review_report_id,
        **output.model_dump(),
        raw_output=result.raw_text,
        input_snapshot_json=snapshot,
        model_name=result.model_name,
        provider_name=result.provider_name,
        prompt_version=prompt.prompt_version,
        schema_version=prompt.schema_version,
        generated_by=actor.id,
        version_no=1,
    )
    session.add(diagnosis)
    session.flush()
    add_ai_usage_log(
        session,
        request_id=request_id,
        scene="product_diagnosis",
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
        target_type="product",
        target_id=str(product.id),
    )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="diagnosis.generate",
        target_type="product_diagnosis",
        target_id=diagnosis.id,
        request_id=request_id,
        detail={
            "product_id": product.id,
            "provider": result.provider_name,
            "model": result.model_name,
            "prompt_version": prompt.prompt_version,
            "missing_data": missing,
        },
    )
    session.commit()
    session.refresh(diagnosis)
    return _diagnosis_response(diagnosis)


def update_diagnosis(
    session: Session,
    *,
    product_id: int,
    diagnosis_id: int,
    payload: DiagnosisUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    diagnosis = get_diagnosis_or_error(session, product_id=product_id, diagnosis_id=diagnosis_id)
    data = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    result = session.execute(
        update(ProductDiagnosis)
        .where(
            ProductDiagnosis.id == diagnosis.id,
            ProductDiagnosis.product_id == product_id,
            ProductDiagnosis.version_no == payload.expected_version,
        )
        .values(
            **data,
            edited_by=actor.id,
            edited_at=_now(),
            version_no=ProductDiagnosis.version_no + 1,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        current = get_diagnosis_or_error(session, product_id=product_id, diagnosis_id=diagnosis_id)
        raise AppError(
            409,
            "DIAGNOSIS_VERSION_CONFLICT",
            "诊断已被其他操作更新，请刷新后重试",
            details={"current_version": current.version_no},
        )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="diagnosis.update",
        target_type="product_diagnosis",
        target_id=diagnosis.id,
        request_id=request_id,
        detail={"product_id": product_id, "changed_fields": sorted(data)},
    )
    session.commit()
    updated = get_diagnosis_or_error(session, product_id=product_id, diagnosis_id=diagnosis_id)
    return _diagnosis_response(updated)
