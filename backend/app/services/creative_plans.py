from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.schemas.creative_plans import (
    CreativePlanGenerateRequest,
    CreativePlanStatusUpdate,
    CreativePlanUpdate,
)
from backend.app.errors import AppError
from backend.app.integrations.ai import AiGenerationError, get_text_provider
from backend.app.integrations.ai.prompts import (
    MainImageDirection,
    MainImagePlanOutput,
    VideoScript,
    VideoScriptOutput,
    build_prompt,
)
from backend.app.models.entities import (
    CreativePlan,
    CreativePlanRevision,
    Product,
    ProductDiagnosis,
    User,
)
from backend.app.services.ai_usage import add_ai_usage_log
from backend.app.services.audit import add_audit_log
from backend.app.services.diagnoses import DIAGNOSIS_FIELDS
from backend.app.services.products import get_product_or_error
from backend.app.services.settings import configured_text_provider

PLAN_MODELS = {
    "main_image": MainImageDirection,
    "video_script": VideoScript,
}
OUTPUT_MODELS = {
    "main_image": MainImagePlanOutput,
    "video_script": VideoScriptOutput,
}
OUTPUT_FIELDS = {"main_image": "directions", "video_script": "scripts"}


def _now() -> datetime:
    return datetime.now(UTC)


def _plan_response(plan: CreativePlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "product_id": plan.product_id,
        "plan_type": plan.plan_type,
        "generation_batch_id": plan.generation_batch_id,
        "title": plan.title,
        "content": plan.content_json or {},
        "rationale": plan.rationale_text,
        "status": plan.status,
        "input_snapshot": plan.input_snapshot_json or {},
        "provider_name": plan.provider_name or "unknown",
        "model_name": plan.model_name or "unknown",
        "prompt_version": plan.prompt_version or "unknown",
        "schema_version": plan.schema_version or "unknown",
        "generated_by": plan.generated_by,
        "edited_by": plan.edited_by,
        "edited_at": plan.edited_at,
        "version_no": plan.version_no,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def _revision_response(revision: CreativePlanRevision) -> dict[str, Any]:
    return {
        "id": revision.id,
        "creative_plan_id": revision.creative_plan_id,
        "version_no": revision.version_no,
        "title": revision.title,
        "content": revision.content_json,
        "rationale": revision.rationale_text,
        "status": revision.status,
        "changed_by": revision.changed_by,
        "created_at": revision.created_at,
    }


def _add_revision(session: Session, plan: CreativePlan, actor_id: int) -> None:
    session.add(
        CreativePlanRevision(
            creative_plan_id=plan.id,
            version_no=plan.version_no,
            title=plan.title,
            content_json=plan.content_json,
            rationale_text=plan.rationale_text,
            status=plan.status,
            changed_by=actor_id,
        )
    )


def get_plan_or_error(
    session: Session,
    *,
    product_id: int,
    plan_id: int,
    for_update: bool = False,
) -> CreativePlan:
    get_product_or_error(session, product_id)
    statement = select(CreativePlan).where(
        CreativePlan.id == plan_id,
        CreativePlan.product_id == product_id,
    )
    if for_update:
        statement = statement.with_for_update()
    plan = session.scalar(statement)
    if plan is None:
        raise AppError(404, "CREATIVE_PLAN_NOT_FOUND", "创意方案不存在或不属于该商品")
    return plan


def _creative_snapshot(
    session: Session,
    *,
    product: Product,
    payload: CreativePlanGenerateRequest,
) -> tuple[dict[str, Any], list[str]]:
    diagnosis_statement = select(ProductDiagnosis).where(ProductDiagnosis.product_id == product.id)
    if payload.diagnosis_id is not None:
        diagnosis_statement = diagnosis_statement.where(ProductDiagnosis.id == payload.diagnosis_id)
    else:
        diagnosis_statement = diagnosis_statement.order_by(ProductDiagnosis.id.desc())
    diagnosis = session.scalar(diagnosis_statement.limit(1))
    if diagnosis is None:
        raise AppError(
            409,
            "DIAGNOSIS_REQUIRED",
            "请先为该商品生成诊断，再生成主图方案或视频脚本",
        )
    source_snapshot = diagnosis.input_snapshot_json or {}
    snapshot = {
        "product": source_snapshot.get("product")
        or {
            "id": product.id,
            "name": product.name,
            "platform": product.platform,
            "category": product.category,
            "price": product.price,
            "target_audience": product.target_audience,
            "selling_points": product.selling_points,
        },
        "competitors": source_snapshot.get("competitors") or [],
        "sku_inventory": source_snapshot.get("sku_inventory") or [],
        "diagnosis": {
            "id": diagnosis.id,
            "version_no": diagnosis.version_no,
            **{field: getattr(diagnosis, field) or "" for field in DIAGNOSIS_FIELDS},
        },
        "operator_notes": payload.notes,
        "snapshot_at": _now(),
    }
    missing = []
    if not snapshot["competitors"]:
        missing.append("竞品数据")
    if not snapshot["sku_inventory"]:
        missing.append("SKU 与库存数据")
    return jsonable_encoder(snapshot), missing


def _log_failure(
    session: Session,
    *,
    request_id: str | None,
    scene: str,
    provider_name: str,
    model_name: str,
    prompt_version: str,
    actor_id: int,
    product_id: int,
    code: str,
    attempts: int = 1,
    latency_ms: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    add_ai_usage_log(
        session,
        request_id=request_id,
        scene=scene,
        provider_name=provider_name,
        model_name=model_name,
        prompt_version=prompt_version,
        status="failed",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        attempts=attempts,
        error_code=code,
        actor_id=actor_id,
        target_type="product",
        target_id=str(product_id),
    )
    session.commit()


def generate_creative_plans(
    session: Session,
    *,
    product_id: int,
    payload: CreativePlanGenerateRequest,
    actor: User,
    request_id: str | None,
) -> list[dict[str, Any]]:
    product = get_product_or_error(session, product_id)
    snapshot, missing = _creative_snapshot(session, product=product, payload=payload)
    prompt = build_prompt(payload.plan_type, snapshot, missing_fields=missing)
    provider = configured_text_provider(get_text_provider, session)
    scene = f"{payload.plan_type}_plan"
    try:
        result = provider.generate_structured(prompt)
    except AiGenerationError as exc:
        _log_failure(
            session,
            request_id=request_id,
            scene=scene,
            provider_name=getattr(provider, "provider_name", "unknown"),
            model_name=getattr(provider, "model_name", "unknown"),
            prompt_version=prompt.prompt_version,
            actor_id=actor.id,
            product_id=product.id,
            code=exc.code,
            attempts=exc.attempts,
            latency_ms=exc.latency_ms,
            input_tokens=exc.usage.input_tokens,
            output_tokens=exc.usage.output_tokens,
            total_tokens=exc.usage.total_tokens,
        )
        status_code = 429 if exc.code == "AI_RATE_LIMITED" else 502
        raise AppError(status_code, exc.code, exc.message) from exc
    except Exception as exc:
        _log_failure(
            session,
            request_id=request_id,
            scene=scene,
            provider_name=getattr(provider, "provider_name", "unknown"),
            model_name=getattr(provider, "model_name", "unknown"),
            prompt_version=prompt.prompt_version,
            actor_id=actor.id,
            product_id=product.id,
            code="AI_GENERATION_FAILED",
        )
        raise AppError(502, "AI_GENERATION_FAILED", "模型生成失败") from exc
    try:
        output = OUTPUT_MODELS[payload.plan_type].model_validate(result.data)
    except ValidationError as exc:
        _log_failure(
            session,
            request_id=request_id,
            scene=scene,
            provider_name=result.provider_name,
            model_name=result.model_name,
            prompt_version=prompt.prompt_version,
            actor_id=actor.id,
            product_id=product.id,
            code="AI_OUTPUT_SCHEMA_INVALID",
            attempts=result.attempts,
            latency_ms=result.latency_ms,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            total_tokens=result.usage.total_tokens,
        )
        raise AppError(502, "AI_OUTPUT_SCHEMA_INVALID", "模型输出未通过创意方案结构校验") from exc
    items = getattr(output, OUTPUT_FIELDS[payload.plan_type])
    batch_id = str(uuid4())
    plans: list[CreativePlan] = []
    for item in items:
        content = item.model_dump(mode="json")
        plan = CreativePlan(
            product_id=product.id,
            plan_type=payload.plan_type,
            generation_batch_id=batch_id,
            title=item.title,
            content_json=content,
            rationale_text=item.rationale,
            status="draft",
            raw_output=result.raw_text,
            input_snapshot_json=snapshot,
            provider_name=result.provider_name,
            model_name=result.model_name,
            prompt_version=prompt.prompt_version,
            schema_version=prompt.schema_version,
            generated_by=actor.id,
            version_no=1,
        )
        session.add(plan)
        session.flush()
        _add_revision(session, plan, actor.id)
        plans.append(plan)
    add_ai_usage_log(
        session,
        request_id=request_id,
        scene=scene,
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
        action="creative_plan.generate",
        target_type="product",
        target_id=product.id,
        request_id=request_id,
        detail={
            "plan_type": payload.plan_type,
            "generation_batch_id": batch_id,
            "plan_ids": [plan.id for plan in plans],
            "diagnosis_id": snapshot["diagnosis"]["id"],
        },
    )
    session.commit()
    for plan in plans:
        session.refresh(plan)
    return [_plan_response(plan) for plan in plans]


def list_creative_plans(
    session: Session,
    *,
    product_id: int,
    plan_type: str,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    filters = [
        CreativePlan.product_id == product_id,
        CreativePlan.plan_type == plan_type,
    ]
    if status:
        filters.append(CreativePlan.status == status)
    total = session.scalar(select(func.count(CreativePlan.id)).where(*filters)) or 0
    rows = session.scalars(
        select(CreativePlan)
        .where(*filters)
        .order_by(CreativePlan.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_plan_response(row) for row in rows], int(total)


def get_creative_plan(session: Session, *, product_id: int, plan_id: int) -> dict[str, Any]:
    return _plan_response(get_plan_or_error(session, product_id=product_id, plan_id=plan_id))


def list_plan_revisions(session: Session, *, product_id: int, plan_id: int) -> list[dict[str, Any]]:
    plan = get_plan_or_error(session, product_id=product_id, plan_id=plan_id)
    revisions = session.scalars(
        select(CreativePlanRevision)
        .where(CreativePlanRevision.creative_plan_id == plan.id)
        .order_by(CreativePlanRevision.version_no.desc())
    ).all()
    return [_revision_response(item) for item in revisions]


def _validated_content(plan_type: str, content: dict[str, Any]) -> dict[str, Any]:
    try:
        return PLAN_MODELS[plan_type].model_validate(content).model_dump(mode="json")
    except (KeyError, ValidationError) as exc:
        raise AppError(
            422,
            "CREATIVE_PLAN_CONTENT_INVALID",
            "创意方案内容不完整或格式不正确",
        ) from exc


def update_creative_plan(
    session: Session,
    *,
    product_id: int,
    plan_id: int,
    payload: CreativePlanUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    plan = get_plan_or_error(session, product_id=product_id, plan_id=plan_id, for_update=True)
    if plan.version_no != payload.expected_version:
        raise AppError(
            409,
            "CREATIVE_PLAN_VERSION_CONFLICT",
            "方案已被其他操作更新，请刷新后重试",
            details={"current_version": plan.version_no},
        )
    if plan.status == "archived":
        raise AppError(409, "CREATIVE_PLAN_ARCHIVED", "归档方案不可再编辑")
    content = _validated_content(plan.plan_type, payload.content)
    plan.content_json = content
    plan.title = str(content["title"])
    plan.rationale_text = str(content["rationale"])
    plan.edited_by = actor.id
    plan.edited_at = _now()
    plan.version_no += 1
    session.flush()
    _add_revision(session, plan, actor.id)
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="creative_plan.update",
        target_type="creative_plan",
        target_id=plan.id,
        request_id=request_id,
        detail={"product_id": product_id, "version_no": plan.version_no},
    )
    session.commit()
    session.refresh(plan)
    return _plan_response(plan)


def update_creative_plan_status(
    session: Session,
    *,
    product_id: int,
    plan_id: int,
    payload: CreativePlanStatusUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    session.scalar(select(Product).where(Product.id == product_id).with_for_update())
    plan = get_plan_or_error(session, product_id=product_id, plan_id=plan_id, for_update=True)
    if plan.version_no != payload.expected_version:
        raise AppError(
            409,
            "CREATIVE_PLAN_VERSION_CONFLICT",
            "方案已被其他操作更新，请刷新后重试",
            details={"current_version": plan.version_no},
        )
    if payload.status == plan.status:
        return _plan_response(plan)
    if plan.status == "archived":
        raise AppError(409, "CREATIVE_PLAN_ARCHIVED", "归档方案不能恢复或选中")
    if payload.status == "archived" and plan.status == "selected":
        raise AppError(
            409,
            "SELECTED_PLAN_CANNOT_ARCHIVE",
            "请先取消选中，再归档方案",
        )
    if payload.status == "selected":
        selected_plans = session.scalars(
            select(CreativePlan)
            .where(
                CreativePlan.product_id == product_id,
                CreativePlan.plan_type == plan.plan_type,
                CreativePlan.status == "selected",
                CreativePlan.id != plan.id,
            )
            .with_for_update()
        ).all()
        for previous in selected_plans:
            previous.status = "draft"
            previous.edited_by = actor.id
            previous.edited_at = _now()
            previous.version_no += 1
            session.flush()
            _add_revision(session, previous, actor.id)
    plan.status = payload.status
    plan.edited_by = actor.id
    plan.edited_at = _now()
    plan.version_no += 1
    session.flush()
    _add_revision(session, plan, actor.id)
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="creative_plan.status.update",
        target_type="creative_plan",
        target_id=plan.id,
        request_id=request_id,
        detail={"product_id": product_id, "status": payload.status},
    )
    session.commit()
    session.refresh(plan)
    return _plan_response(plan)
