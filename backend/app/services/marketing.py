import hashlib
import hmac
import ipaddress
import secrets
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.app.api.schemas.marketing import (
    AdExperimentGenerateRequest,
    AdExperimentUpdate,
    AdRecommendationConfirmation,
    AdRecommendationGenerateRequest,
    AdRecommendationUpdate,
    PromotionLinkCreate,
    PromotionLinkSuggestionRequest,
    PromotionLinkUpdate,
)
from backend.app.config import get_settings
from backend.app.errors import AppError
from backend.app.integrations.ai import AiGenerationError, get_text_provider
from backend.app.integrations.ai.prompts import AdRecommendationOutput, build_prompt
from backend.app.models.entities import (
    AdExperiment,
    AdRecommendation,
    GeneratedAsset,
    ProductDiagnosis,
    PromotionLink,
    PromotionLinkClick,
    User,
)
from backend.app.services.ai_usage import add_ai_usage_log
from backend.app.services.audit import add_audit_log
from backend.app.services.products import get_product_or_error
from backend.app.services.settings import configured_text_provider

UTM_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
BOT_MARKERS = ("bot", "spider", "crawler", "slurp", "headless", "preview")
EXPERIMENT_TRANSITIONS = {
    "draft": {"confirmed", "cancelled"},
    "confirmed": {"running", "cancelled"},
    "running": {"finished", "cancelled"},
    "finished": set(),
    "cancelled": set(),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_target_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except ValueError as exc:
        raise AppError(422, "PROMOTION_TARGET_URL_INVALID", "推广目标 URL 格式无效") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise AppError(422, "PROMOTION_TARGET_URL_INVALID", "推广目标仅支持公开 HTTP(S) URL")
    if parsed.username or parsed.password:
        raise AppError(422, "PROMOTION_TARGET_URL_INVALID", "推广目标 URL 不能包含认证信息")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".local"):
        raise AppError(422, "PROMOTION_TARGET_URL_UNSAFE", "推广目标不能指向本机或内网")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise AppError(422, "PROMOTION_TARGET_URL_UNSAFE", "推广目标不能指向本机或内网")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, ""))


def _validate_utm(value: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, raw in value.items():
        if key not in UTM_KEYS:
            raise AppError(422, "PROMOTION_UTM_INVALID", f"不支持的 UTM 字段：{key}")
        if not isinstance(raw, str):
            raise AppError(422, "PROMOTION_UTM_INVALID", "UTM 值必须是字符串")
        normalized = raw.strip()
        if len(normalized) > 200:
            raise AppError(422, "PROMOTION_UTM_INVALID", "单个 UTM 值不能超过 200 个字符")
        if normalized:
            result[key] = normalized
    return result


def _redirect_url(link: PromotionLink) -> str:
    parsed = urlsplit(link.target_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(link.utm_json or {})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _link_response(link: PromotionLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "product_id": link.product_id,
        "link_name": link.link_name,
        "target_url": link.target_url,
        "redirect_path": f"/api/v1/r/{link.tracking_code}",
        "tracking_code": link.tracking_code,
        "utm": link.utm_json or {},
        "status": link.status,
        "click_count": link.click_count,
        "scene_text": link.scene_text,
        "lock_version": link.lock_version,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


def get_promotion_link_or_error(
    session: Session, *, product_id: int, link_id: int
) -> PromotionLink:
    get_product_or_error(session, product_id)
    link = session.scalar(
        select(PromotionLink).where(
            PromotionLink.id == link_id, PromotionLink.product_id == product_id
        )
    )
    if link is None:
        raise AppError(404, "PROMOTION_LINK_NOT_FOUND", "推广链接不存在或不属于该商品")
    return link


def suggest_promotion_links(
    session: Session, *, product_id: int, payload: PromotionLinkSuggestionRequest
) -> list[dict[str, Any]]:
    product = get_product_or_error(session, product_id)
    raw_target = payload.target_url or product.product_url
    if not raw_target:
        raise AppError(422, "PROMOTION_TARGET_URL_REQUIRED", "请先补充商品链接或指定推广目标 URL")
    target = _validate_target_url(raw_target)
    campaign = f"product_{product.id}"
    return [
        {
            "link_name": "内容种草链接",
            "target_url": target,
            "scene_text": "适用于内容、图文和短视频自然触达",
            "utm": {"utm_source": "content", "utm_medium": "organic", "utm_campaign": campaign},
        },
        {
            "link_name": "付费素材测试链接",
            "target_url": target,
            "scene_text": "适用于小预算素材与人群组合测试",
            "utm": {"utm_source": "paid", "utm_medium": "cpc", "utm_campaign": campaign},
        },
        {
            "link_name": "私域触达链接",
            "target_url": target,
            "scene_text": "适用于社群、客服和老客触达",
            "utm": {"utm_source": "private", "utm_medium": "message", "utm_campaign": campaign},
        },
    ]


def create_promotion_link(
    session: Session,
    *,
    product_id: int,
    payload: PromotionLinkCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    get_product_or_error(session, product_id)
    link = PromotionLink(
        product_id=product_id,
        link_name=payload.link_name,
        target_url=_validate_target_url(payload.target_url),
        tracking_code=secrets.token_urlsafe(18),
        utm_json=_validate_utm(payload.utm),
        scene_text=payload.scene_text,
        status="active",
        click_count=0,
        lock_version=1,
    )
    session.add(link)
    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="promotion_link.create",
        target_type="promotion_link",
        target_id=link.id,
        request_id=request_id,
        detail={"product_id": product_id, "status": "active"},
    )
    session.commit()
    session.refresh(link)
    return _link_response(link)


def list_promotion_links(
    session: Session,
    *,
    product_id: int,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    conditions = [PromotionLink.product_id == product_id]
    if status:
        conditions.append(PromotionLink.status == status)
    total = session.scalar(select(func.count(PromotionLink.id)).where(*conditions)) or 0
    rows = session.scalars(
        select(PromotionLink)
        .where(*conditions)
        .order_by(PromotionLink.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_link_response(row) for row in rows], int(total)


def update_promotion_link(
    session: Session,
    *,
    product_id: int,
    link_id: int,
    payload: PromotionLinkUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    link = get_promotion_link_or_error(session, product_id=product_id, link_id=link_id)
    values = payload.model_dump(exclude_unset=True, exclude={"expected_version", "utm"})
    if "target_url" in values:
        values["target_url"] = _validate_target_url(values["target_url"])
    if "utm" in payload.model_fields_set:
        values["utm_json"] = _validate_utm(payload.utm or {})
    result = session.execute(
        update(PromotionLink)
        .where(PromotionLink.id == link.id, PromotionLink.lock_version == payload.expected_version)
        .values(**values, lock_version=PromotionLink.lock_version + 1, updated_at=_now())
    )
    if result.rowcount != 1:
        session.rollback()
        current = get_promotion_link_or_error(session, product_id=product_id, link_id=link_id)
        raise AppError(
            409,
            "PROMOTION_LINK_VERSION_CONFLICT",
            "推广链接已被其他操作更新，请刷新后重试",
            details={"current_version": current.lock_version},
        )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="promotion_link.update",
        target_type="promotion_link",
        target_id=link.id,
        request_id=request_id,
        detail={"product_id": product_id, "changed_fields": sorted(values)},
    )
    session.commit()
    return _link_response(
        get_promotion_link_or_error(session, product_id=product_id, link_id=link_id)
    )


def record_promotion_click(
    session: Session, *, tracking_code: str, client_ip: str | None, user_agent: str | None
) -> str:
    link = session.scalar(
        select(PromotionLink).where(PromotionLink.tracking_code == tracking_code).with_for_update()
    )
    if link is None or link.status != "active":
        raise AppError(404, "PROMOTION_LINK_UNAVAILABLE", "推广链接不存在或已停用")
    target = _redirect_url(link)
    _validate_target_url(target)
    now = _now()
    ip_hash = None
    if client_ip:
        secret = get_settings().jwt_secret.get_secret_value().encode()
        ip_hash = hmac.new(secret, client_ip.encode(), hashlib.sha256).hexdigest()
    normalized_agent = (user_agent or "")[:1000]
    reason = None
    if any(marker in normalized_agent.casefold() for marker in BOT_MARKERS):
        reason = "suspected_bot"
    elif ip_hash:
        duplicate = session.scalar(
            select(PromotionLinkClick.id)
            .where(
                PromotionLinkClick.promotion_link_id == link.id,
                PromotionLinkClick.client_ip_hash == ip_hash,
                PromotionLinkClick.is_counted.is_(True),
                PromotionLinkClick.clicked_at >= now - timedelta(minutes=10),
            )
            .limit(1)
        )
        if duplicate is not None:
            reason = "duplicate_10m"
    counted = reason is None
    session.add(
        PromotionLinkClick(
            promotion_link_id=link.id,
            clicked_at=now,
            client_ip_hash=ip_hash,
            user_agent=normalized_agent or None,
            is_counted=counted,
            filter_reason=reason,
        )
    )
    if counted:
        link.click_count += 1
    session.commit()
    return target


def promotion_link_statistics(
    session: Session,
    *,
    product_id: int,
    link_id: int,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    get_promotion_link_or_error(session, product_id=product_id, link_id=link_id)
    if period_end < period_start or (period_end - period_start).days > 366:
        raise AppError(422, "PROMOTION_STAT_PERIOD_INVALID", "统计周期无效或超过 366 天")
    start_at = datetime.combine(period_start, time.min, tzinfo=UTC)
    end_at = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=UTC)
    rows = session.scalars(
        select(PromotionLinkClick).where(
            PromotionLinkClick.promotion_link_id == link_id,
            PromotionLinkClick.clicked_at >= start_at,
            PromotionLinkClick.clicked_at < end_at,
        )
    ).all()
    buckets: dict[date, dict[str, Any]] = {}
    for row in rows:
        day = row.clicked_at.date()
        bucket = buckets.setdefault(day, {"counted": 0, "filtered": 0, "visitors": set()})
        if row.is_counted:
            bucket["counted"] += 1
            if row.client_ip_hash:
                bucket["visitors"].add(row.client_ip_hash)
        else:
            bucket["filtered"] += 1
    all_visitors = {row.client_ip_hash for row in rows if row.is_counted and row.client_ip_hash}
    return {
        "promotion_link_id": link_id,
        "period_start": period_start,
        "period_end": period_end,
        "counted_clicks": sum(1 for row in rows if row.is_counted),
        "filtered_clicks": sum(1 for row in rows if not row.is_counted),
        "unique_visitors": len(all_visitors),
        "daily": [
            {
                "day": day,
                "counted_clicks": data["counted"],
                "filtered_clicks": data["filtered"],
                "unique_visitors": len(data["visitors"]),
            }
            for day, data in sorted(buckets.items())
        ],
    }


def _recommendation_response(item: AdRecommendation) -> dict[str, Any]:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "summary_text": item.summary_text or "",
        "objective_text": item.objective_text or "",
        "audience_segments": item.audience_segments_json or [],
        "budget_plan": item.budget_plan_json or {},
        "creative_tests": item.creative_tests_json or [],
        "bid_strategy": item.bid_strategy_json or {},
        "risk_controls": item.risk_controls_json or [],
        "next_steps": item.next_steps_json or [],
        "confirm_status": item.confirm_status,
        "confirmed_by": item.confirmed_by,
        "confirmed_at": item.confirmed_at,
        "confirm_remark": item.confirm_remark,
        "input_snapshot": item.input_snapshot_json or {},
        "provider_name": item.provider_name or "unknown",
        "model_name": item.model_name or "unknown",
        "prompt_version": item.prompt_version or "unknown",
        "schema_version": item.schema_version or "unknown",
        "generated_by": item.generated_by,
        "version_no": item.version_no,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def get_recommendation_or_error(
    session: Session, *, product_id: int, recommendation_id: int
) -> AdRecommendation:
    get_product_or_error(session, product_id)
    item = session.scalar(
        select(AdRecommendation).where(
            AdRecommendation.id == recommendation_id,
            AdRecommendation.product_id == product_id,
        )
    )
    if item is None:
        raise AppError(404, "AD_RECOMMENDATION_NOT_FOUND", "投放建议不存在或不属于该商品")
    return item


def list_ad_recommendations(
    session: Session, *, product_id: int, page: int, page_size: int
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    total = (
        session.scalar(
            select(func.count(AdRecommendation.id)).where(AdRecommendation.product_id == product_id)
        )
        or 0
    )
    rows = session.scalars(
        select(AdRecommendation)
        .where(AdRecommendation.product_id == product_id)
        .order_by(AdRecommendation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_recommendation_response(row) for row in rows], int(total)


def generate_ad_recommendation(
    session: Session,
    *,
    product_id: int,
    payload: AdRecommendationGenerateRequest,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    product = get_product_or_error(session, product_id)
    assets = session.scalars(
        select(GeneratedAsset).where(GeneratedAsset.id.in_(payload.asset_ids))
    ).all()
    links = session.scalars(
        select(PromotionLink).where(PromotionLink.id.in_(payload.link_ids))
    ).all()
    if len(assets) != len(payload.asset_ids) or any(
        item.product_id != product_id
        or item.review_status != "approved"
        or item.file_status != "available"
        for item in assets
    ):
        raise AppError(422, "AD_ASSET_INVALID", "投放建议只能使用本商品已审核且文件可用的素材")
    if len(links) != len(payload.link_ids) or any(
        item.product_id != product_id or item.status != "active" for item in links
    ):
        raise AppError(422, "AD_LINK_INVALID", "投放建议只能使用本商品的有效推广链接")
    diagnosis = session.scalar(
        select(ProductDiagnosis)
        .where(ProductDiagnosis.product_id == product_id)
        .order_by(ProductDiagnosis.id.desc())
        .limit(1)
    )
    snapshot = jsonable_encoder(
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
            "latest_diagnosis": (
                {
                    "id": diagnosis.id,
                    "positioning": diagnosis.positioning,
                    "audience_insights": diagnosis.audience_insights,
                    "risks": diagnosis.risks,
                    "recommendations": diagnosis.recommendations,
                }
                if diagnosis
                else None
            ),
            "approved_assets": [
                {
                    "id": item.id,
                    "type": item.asset_type,
                    "usage_scene": item.usage_scene,
                    "score": item.score,
                    "tags": item.tags_json or [],
                }
                for item in assets
            ],
            "promotion_links": [
                {
                    "id": item.id,
                    "name": item.link_name,
                    "scene": item.scene_text,
                    "utm": item.utm_json or {},
                }
                for item in links
            ],
            "operator_notes": payload.notes,
            "snapshot_at": _now(),
        }
    )
    missing = [] if diagnosis else ["商品诊断"]
    prompt = build_prompt("ad_recommendation", snapshot, missing_fields=missing)
    provider = configured_text_provider(get_text_provider, session)
    try:
        result = provider.generate_structured(prompt)
        output = AdRecommendationOutput.model_validate(result.data)
    except AiGenerationError as exc:
        add_ai_usage_log(
            session,
            request_id=request_id,
            scene="ad_recommendation",
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
            scene="ad_recommendation",
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
        raise AppError(502, "AI_OUTPUT_SCHEMA_INVALID", "模型输出未通过投放建议结构校验") from exc
    except Exception as exc:
        add_ai_usage_log(
            session,
            request_id=request_id,
            scene="ad_recommendation",
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
    item = AdRecommendation(
        product_id=product_id,
        summary_text=output.strategy_summary,
        objective_text=output.objective,
        audience_segments_json=[{"segment": "建议人群", "strategy": output.target_audience}],
        budget_plan_json={"plan": output.budget_plan},
        creative_tests_json=[{"plan": output.creative_test_plan}],
        bid_strategy_json={"strategy": output.bidding_strategy},
        risk_controls_json=[output.risks],
        next_steps_json=[output.next_actions],
        confirm_status="pending",
        model_name=result.model_name,
        provider_name=result.provider_name,
        prompt_version=prompt.prompt_version,
        schema_version=prompt.schema_version,
        input_snapshot_json=snapshot,
        raw_output=result.raw_text,
        generated_by=actor.id,
        version_no=1,
    )
    session.add(item)
    session.flush()
    add_ai_usage_log(
        session,
        request_id=request_id,
        scene="ad_recommendation",
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
        target_type="ad_recommendation",
        target_id=str(item.id),
    )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="ad_recommendation.generate",
        target_type="ad_recommendation",
        target_id=item.id,
        request_id=request_id,
        detail={
            "product_id": product_id,
            "asset_ids": payload.asset_ids,
            "link_ids": payload.link_ids,
        },
    )
    session.commit()
    session.refresh(item)
    return _recommendation_response(item)


def confirm_ad_recommendation(
    session: Session,
    *,
    product_id: int,
    recommendation_id: int,
    payload: AdRecommendationConfirmation,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    item = get_recommendation_or_error(
        session, product_id=product_id, recommendation_id=recommendation_id
    )
    if item.confirm_status != "pending":
        raise AppError(409, "AD_RECOMMENDATION_FINAL", "投放建议已完成确认，不能重复操作")
    result = session.execute(
        update(AdRecommendation)
        .where(
            AdRecommendation.id == item.id,
            AdRecommendation.confirm_status == "pending",
            AdRecommendation.version_no == payload.expected_version,
        )
        .values(
            confirm_status=payload.confirm_status,
            confirmed_by=actor.id,
            confirmed_at=_now(),
            confirm_remark=payload.remark,
            version_no=AdRecommendation.version_no + 1,
            updated_at=_now(),
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise AppError(409, "AD_RECOMMENDATION_VERSION_CONFLICT", "投放建议已被其他操作更新")
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action=f"ad_recommendation.{payload.confirm_status}",
        target_type="ad_recommendation",
        target_id=item.id,
        request_id=request_id,
        detail={"product_id": product_id, "remark": payload.remark},
    )
    session.commit()
    return _recommendation_response(
        get_recommendation_or_error(
            session, product_id=product_id, recommendation_id=recommendation_id
        )
    )


def update_ad_recommendation(
    session: Session,
    *,
    product_id: int,
    recommendation_id: int,
    payload: AdRecommendationUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    item = get_recommendation_or_error(
        session, product_id=product_id, recommendation_id=recommendation_id
    )
    if item.confirm_status != "pending":
        raise AppError(409, "AD_RECOMMENDATION_CONTENT_LOCKED", "建议确认或驳回后内容已锁定")
    source = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    mapping: dict[str, Any] = {
        "strategy_summary": ("summary_text", lambda value: value),
        "objective": ("objective_text", lambda value: value),
        "target_audience": (
            "audience_segments_json",
            lambda value: [{"segment": "建议人群", "strategy": value}],
        ),
        "budget_plan": ("budget_plan_json", lambda value: {"plan": value}),
        "creative_test_plan": (
            "creative_tests_json",
            lambda value: [{"plan": value}],
        ),
        "bidding_strategy": (
            "bid_strategy_json",
            lambda value: {"strategy": value},
        ),
        "risks": ("risk_controls_json", lambda value: [value]),
        "next_actions": ("next_steps_json", lambda value: [value]),
    }
    values = {mapping[key][0]: mapping[key][1](value) for key, value in source.items()}
    result = session.execute(
        update(AdRecommendation)
        .where(
            AdRecommendation.id == item.id,
            AdRecommendation.confirm_status == "pending",
            AdRecommendation.version_no == payload.expected_version,
        )
        .values(
            **values,
            version_no=AdRecommendation.version_no + 1,
            updated_at=_now(),
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise AppError(
            409,
            "AD_RECOMMENDATION_VERSION_CONFLICT",
            "投放建议已被其他操作更新，请刷新后重试",
        )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="ad_recommendation.update",
        target_type="ad_recommendation",
        target_id=item.id,
        request_id=request_id,
        detail={"product_id": product_id, "changed_fields": sorted(source)},
    )
    session.commit()
    return _recommendation_response(
        get_recommendation_or_error(
            session, product_id=product_id, recommendation_id=recommendation_id
        )
    )


def _experiment_response(item: AdExperiment) -> dict[str, Any]:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "recommendation_id": item.recommendation_id,
        "related_asset_id": item.related_asset_id,
        "related_link_id": item.related_link_id,
        "experiment_name": item.experiment_name,
        "target_text": item.target_text,
        "audience_text": item.audience_text,
        "budget_amount": item.budget_amount,
        "success_metric_text": item.success_metric_text,
        "hypothesis_text": item.hypothesis_text,
        "experiment_status": item.experiment_status,
        "version_no": item.version_no,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def get_experiment_or_error(
    session: Session, *, product_id: int, experiment_id: int
) -> AdExperiment:
    get_product_or_error(session, product_id)
    item = session.scalar(
        select(AdExperiment).where(
            AdExperiment.id == experiment_id, AdExperiment.product_id == product_id
        )
    )
    if item is None:
        raise AppError(404, "AD_EXPERIMENT_NOT_FOUND", "投放实验不存在或不属于该商品")
    return item


def list_ad_experiments(
    session: Session,
    *,
    product_id: int,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    conditions = [AdExperiment.product_id == product_id]
    if status:
        conditions.append(AdExperiment.experiment_status == status)
    total = session.scalar(select(func.count(AdExperiment.id)).where(*conditions)) or 0
    rows = session.scalars(
        select(AdExperiment)
        .where(*conditions)
        .order_by(AdExperiment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_experiment_response(row) for row in rows], int(total)


def generate_ad_experiment(
    session: Session,
    *,
    product_id: int,
    payload: AdExperimentGenerateRequest,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    recommendation = get_recommendation_or_error(
        session, product_id=product_id, recommendation_id=payload.recommendation_id
    )
    if recommendation.confirm_status != "confirmed":
        raise AppError(409, "AD_RECOMMENDATION_NOT_CONFIRMED", "只有已确认的投放建议才能生成实验")
    asset = session.get(GeneratedAsset, payload.related_asset_id)
    if (
        asset is None
        or asset.product_id != product_id
        or asset.review_status != "approved"
        or asset.file_status != "available"
    ):
        raise AppError(422, "AD_EXPERIMENT_ASSET_INVALID", "实验素材必须属于本商品且已审核可用")
    link = session.get(PromotionLink, payload.related_link_id)
    if link is None or link.product_id != product_id or link.status != "active":
        raise AppError(422, "AD_EXPERIMENT_LINK_INVALID", "实验链接必须属于本商品且处于启用状态")
    audience = recommendation.audience_segments_json or []
    item = AdExperiment(
        product_id=product_id,
        recommendation_id=recommendation.id,
        related_asset_id=asset.id,
        related_link_id=link.id,
        experiment_name=payload.experiment_name or f"投放实验 #{recommendation.id}",
        target_text=recommendation.objective_text,
        audience_text="\n".join(
            str(value.get("strategy") or value.get("segment") or "")
            for value in audience
            if isinstance(value, dict)
        )
        or None,
        budget_amount=payload.budget_amount,
        success_metric_text="以点击率、转化率和投入产出比作为人工复盘指标",
        hypothesis_text=recommendation.summary_text,
        experiment_status="draft",
        version_no=1,
    )
    session.add(item)
    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="ad_experiment.generate",
        target_type="ad_experiment",
        target_id=item.id,
        request_id=request_id,
        detail={"product_id": product_id, "recommendation_id": recommendation.id},
    )
    session.commit()
    session.refresh(item)
    return _experiment_response(item)


def update_ad_experiment(
    session: Session,
    *,
    product_id: int,
    experiment_id: int,
    payload: AdExperimentUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    item = get_experiment_or_error(session, product_id=product_id, experiment_id=experiment_id)
    values = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    requested_status = values.get("experiment_status")
    content_fields = set(values) - {"experiment_status"}
    if content_fields and item.experiment_status != "draft":
        raise AppError(409, "AD_EXPERIMENT_CONTENT_LOCKED", "实验确认后内容已锁定")
    if requested_status is not None:
        allowed = EXPERIMENT_TRANSITIONS[item.experiment_status]
        if requested_status not in allowed:
            raise AppError(
                409,
                "AD_EXPERIMENT_TRANSITION_INVALID",
                f"实验不能从 {item.experiment_status} 变更为 {requested_status}",
            )
    result = session.execute(
        update(AdExperiment)
        .where(
            AdExperiment.id == item.id,
            AdExperiment.version_no == payload.expected_version,
        )
        .values(**values, version_no=AdExperiment.version_no + 1, updated_at=_now())
    )
    if result.rowcount != 1:
        session.rollback()
        current = get_experiment_or_error(
            session, product_id=product_id, experiment_id=experiment_id
        )
        raise AppError(
            409,
            "AD_EXPERIMENT_VERSION_CONFLICT",
            "实验已被其他操作更新，请刷新后重试",
            details={"current_version": current.version_no},
        )
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="ad_experiment.update",
        target_type="ad_experiment",
        target_id=item.id,
        request_id=request_id,
        detail={"product_id": product_id, "changed_fields": sorted(values)},
    )
    session.commit()
    return _experiment_response(
        get_experiment_or_error(session, product_id=product_id, experiment_id=experiment_id)
    )
