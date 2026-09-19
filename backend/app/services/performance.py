from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.app.api.schemas.performance import (
    PerformanceRecordCreate,
    PerformanceRecordUpdate,
)
from backend.app.errors import AppError
from backend.app.models.entities import (
    AdExperiment,
    CreativePlan,
    GeneratedAsset,
    PerformanceRecord,
    Product,
    PromotionLink,
    User,
)
from backend.app.services.audit import add_audit_log
from backend.app.services.products import get_product_or_error

RATE_QUANTUM = Decimal("0.000001")


def _now() -> datetime:
    return datetime.now(UTC)


def _rate(numerator: int | Decimal, denominator: int | Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        RATE_QUANTUM, rounding=ROUND_HALF_UP
    )


def calculate_metrics(
    *, impressions: int, clicks: int, conversions: int, spend: Decimal, revenue: Decimal
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    return (
        _rate(clicks, impressions),
        _rate(conversions, clicks),
        _rate(revenue, spend),
    )


def _response(item: PerformanceRecord) -> dict[str, Any]:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "creative_plan_id": item.creative_plan_id,
        "generated_asset_id": item.generated_asset_id,
        "promotion_link_id": item.promotion_link_id,
        "experiment_id": item.experiment_id,
        "period_start": item.period_start,
        "period_end": item.period_end,
        "impressions": item.impressions,
        "clicks": item.clicks,
        "ctr": item.ctr,
        "conversions": item.conversions,
        "conversion_rate": item.conversion_rate,
        "spend": item.spend,
        "revenue": item.revenue,
        "roi": item.roi,
        "notes": item.notes,
        "record_status": item.record_status,
        "version_no": item.version_no,
        "created_by": item.created_by,
        "updated_by": item.updated_by,
        "voided_by": item.voided_by,
        "voided_at": item.voided_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def get_performance_record_or_error(
    session: Session, *, product_id: int, record_id: int
) -> PerformanceRecord:
    get_product_or_error(session, product_id)
    item = session.scalar(
        select(PerformanceRecord).where(
            PerformanceRecord.id == record_id,
            PerformanceRecord.product_id == product_id,
        )
    )
    if item is None:
        raise AppError(404, "PERFORMANCE_RECORD_NOT_FOUND", "经营记录不存在或不属于该商品")
    return item


def _validate_reference(
    session: Session,
    *,
    model: type,
    object_id: int | None,
    product_id: int,
    code: str,
    message: str,
) -> None:
    if object_id is None:
        return
    item = session.get(model, object_id)
    if item is None or item.product_id != product_id:
        raise AppError(422, code, message)


def _validate_references(
    session: Session, *, product_id: int, payload: PerformanceRecordCreate
) -> None:
    for model, object_id, code, message in (
        (
            CreativePlan,
            payload.creative_plan_id,
            "PERFORMANCE_PLAN_INVALID",
            "创意方案不属于该商品",
        ),
        (
            GeneratedAsset,
            payload.generated_asset_id,
            "PERFORMANCE_ASSET_INVALID",
            "素材不属于该商品",
        ),
        (
            PromotionLink,
            payload.promotion_link_id,
            "PERFORMANCE_LINK_INVALID",
            "推广链接不属于该商品",
        ),
        (
            AdExperiment,
            payload.experiment_id,
            "PERFORMANCE_EXPERIMENT_INVALID",
            "实验不属于该商品",
        ),
    ):
        _validate_reference(
            session,
            model=model,
            object_id=object_id,
            product_id=product_id,
            code=code,
            message=message,
        )


def _lock_product(session: Session, product_id: int) -> Product:
    product = session.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if product is None:
        raise AppError(404, "PRODUCT_NOT_FOUND", "商品不存在或无权访问")
    return product


def _ensure_period_available(
    session: Session,
    *,
    product_id: int,
    period_start: date,
    period_end: date,
    exclude_id: int | None = None,
) -> None:
    conditions = [
        PerformanceRecord.product_id == product_id,
        PerformanceRecord.record_status == "active",
        PerformanceRecord.period_start <= period_end,
        PerformanceRecord.period_end >= period_start,
    ]
    if exclude_id is not None:
        conditions.append(PerformanceRecord.id != exclude_id)
    conflict = session.scalar(select(PerformanceRecord.id).where(*conditions).limit(1))
    if conflict is not None:
        raise AppError(
            409,
            "PERFORMANCE_PERIOD_OVERLAP",
            "该商品已存在与此周期重叠的有效经营记录",
            details={"conflict_record_id": conflict},
        )


def create_performance_record(
    session: Session,
    *,
    product_id: int,
    payload: PerformanceRecordCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    _lock_product(session, product_id)
    _validate_references(session, product_id=product_id, payload=payload)
    _ensure_period_available(
        session,
        product_id=product_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    ctr, conversion_rate, roi = calculate_metrics(
        impressions=payload.impressions,
        clicks=payload.clicks,
        conversions=payload.conversions,
        spend=payload.spend,
        revenue=payload.revenue,
    )
    item = PerformanceRecord(
        product_id=product_id,
        **payload.model_dump(),
        ctr=ctr,
        conversion_rate=conversion_rate,
        roi=roi,
        record_status="active",
        version_no=1,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(item)
    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="performance_record.create",
        target_type="performance_record",
        target_id=item.id,
        request_id=request_id,
        detail={
            "product_id": product_id,
            "period": [str(payload.period_start), str(payload.period_end)],
        },
    )
    session.commit()
    session.refresh(item)
    return _response(item)


def list_performance_records(
    session: Session,
    *,
    product_id: int,
    status: str | None,
    period_start: date | None,
    period_end: date | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    conditions = [PerformanceRecord.product_id == product_id]
    if status:
        conditions.append(PerformanceRecord.record_status == status)
    if period_start:
        conditions.append(PerformanceRecord.period_end >= period_start)
    if period_end:
        conditions.append(PerformanceRecord.period_start <= period_end)
    total = session.scalar(select(func.count(PerformanceRecord.id)).where(*conditions)) or 0
    rows = session.scalars(
        select(PerformanceRecord)
        .where(*conditions)
        .order_by(PerformanceRecord.period_start.desc(), PerformanceRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_response(item) for item in rows], int(total)


def performance_summary(
    session: Session,
    *,
    product_id: int,
    period_start: date | None,
    period_end: date | None,
) -> dict[str, Any]:
    get_product_or_error(session, product_id)
    conditions = [
        PerformanceRecord.product_id == product_id,
        PerformanceRecord.record_status == "active",
    ]
    if period_start:
        conditions.append(PerformanceRecord.period_end >= period_start)
    if period_end:
        conditions.append(PerformanceRecord.period_start <= period_end)
    rows = session.scalars(select(PerformanceRecord).where(*conditions)).all()
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
    return {
        "period_start": min((item.period_start for item in rows), default=None),
        "period_end": max((item.period_end for item in rows), default=None),
        "record_count": len(rows),
        "impressions": impressions,
        "clicks": clicks,
        "ctr": ctr,
        "conversions": conversions,
        "conversion_rate": conversion_rate,
        "spend": spend,
        "revenue": revenue,
        "roi": roi,
    }


def update_performance_record(
    session: Session,
    *,
    product_id: int,
    record_id: int,
    payload: PerformanceRecordUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    item = get_performance_record_or_error(session, product_id=product_id, record_id=record_id)
    if item.record_status != "active":
        raise AppError(409, "PERFORMANCE_RECORD_VOIDED", "已作废经营记录不能编辑")
    _lock_product(session, product_id)
    base_payload = PerformanceRecordCreate.model_validate(
        payload.model_dump(exclude={"expected_version"})
    )
    _validate_references(session, product_id=product_id, payload=base_payload)
    _ensure_period_available(
        session,
        product_id=product_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        exclude_id=item.id,
    )
    ctr, conversion_rate, roi = calculate_metrics(
        impressions=payload.impressions,
        clicks=payload.clicks,
        conversions=payload.conversions,
        spend=payload.spend,
        revenue=payload.revenue,
    )
    values = payload.model_dump(exclude={"expected_version"})
    result = session.execute(
        update(PerformanceRecord)
        .where(
            PerformanceRecord.id == item.id,
            PerformanceRecord.record_status == "active",
            PerformanceRecord.version_no == payload.expected_version,
        )
        .values(
            **values,
            ctr=ctr,
            conversion_rate=conversion_rate,
            roi=roi,
            updated_by=actor.id,
            updated_at=_now(),
            version_no=PerformanceRecord.version_no + 1,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise AppError(409, "PERFORMANCE_VERSION_CONFLICT", "经营记录已被其他操作更新")
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="performance_record.update",
        target_type="performance_record",
        target_id=item.id,
        request_id=request_id,
        detail={"product_id": product_id},
    )
    session.commit()
    return _response(
        get_performance_record_or_error(session, product_id=product_id, record_id=record_id)
    )


def void_performance_record(
    session: Session,
    *,
    product_id: int,
    record_id: int,
    expected_version: int,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    item = get_performance_record_or_error(session, product_id=product_id, record_id=record_id)
    if item.record_status != "active":
        raise AppError(409, "PERFORMANCE_RECORD_VOIDED", "经营记录已作废")
    result = session.execute(
        update(PerformanceRecord)
        .where(
            PerformanceRecord.id == item.id,
            PerformanceRecord.record_status == "active",
            PerformanceRecord.version_no == expected_version,
        )
        .values(
            record_status="voided",
            voided_by=actor.id,
            voided_at=_now(),
            updated_by=actor.id,
            updated_at=_now(),
            version_no=PerformanceRecord.version_no + 1,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise AppError(409, "PERFORMANCE_VERSION_CONFLICT", "经营记录已被其他操作更新")
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="performance_record.void",
        target_type="performance_record",
        target_id=item.id,
        request_id=request_id,
        detail={"product_id": product_id},
    )
    session.commit()
    return _response(
        get_performance_record_or_error(session, product_id=product_id, record_id=record_id)
    )
