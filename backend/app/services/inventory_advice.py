from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.schemas.inventory_advice import InventoryAdviceGenerateRequest
from backend.app.errors import AppError
from backend.app.models.entities import (
    InventoryAdviceItem,
    InventoryAdviceRun,
    InventoryItem,
    InventoryMovement,
    Product,
    ProductSku,
    Store,
    User,
)
from backend.app.services.audit import add_audit_log
from backend.app.services.stores import get_store_or_error

RULE_VERSION = "inventory-rule-v1"


def _get_run_for_store(session: Session, *, store_id: int, run_id: int) -> InventoryAdviceRun:
    get_store_or_error(session, store_id)
    run = session.scalar(
        select(InventoryAdviceRun).where(
            InventoryAdviceRun.id == run_id,
            InventoryAdviceRun.store_id == store_id,
        )
    )
    if run is None:
        raise AppError(404, "INVENTORY_ADVICE_NOT_FOUND", "库存建议不存在或不属于该店铺")
    return run


def _run_summary(run: InventoryAdviceRun, store: Store) -> dict[str, Any]:
    return {
        "id": run.id,
        "store_id": run.store_id,
        "store_name": store.store_name,
        "rule_version": run.rule_version,
        "lookback_days": run.lookback_days,
        "coverage_days": run.coverage_days,
        "safety_multiplier": run.safety_multiplier,
        "min_outbound_events": run.min_outbound_events,
        "item_count": run.item_count,
        "replenish_count": run.replenish_count,
        "insufficient_count": run.insufficient_count,
        "message": run.message,
        "generated_by": run.generated_by,
        "generated_at": run.generated_at,
    }


def _item_response(
    item: InventoryAdviceItem,
    *,
    product_name: str,
    sku_code: str,
    sku_name: str,
) -> dict[str, Any]:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "product_name": product_name,
        "sku_id": item.sku_id,
        "sku_code": sku_code,
        "sku_name": sku_name,
        "stock_qty": item.stock_qty,
        "locked_qty": item.locked_qty,
        "available_qty": item.available_qty,
        "warning_threshold": item.warning_threshold,
        "outbound_qty": item.outbound_qty,
        "outbound_events": item.outbound_events,
        "daily_outbound_rate": item.daily_outbound_rate,
        "target_stock_qty": item.target_stock_qty,
        "suggested_restock_qty": item.suggested_restock_qty,
        "action": item.action,
        "priority": item.priority,
        "data_status": item.data_status,
        "explanation": item.explanation,
    }


def get_inventory_advice_run(session: Session, *, store_id: int, run_id: int) -> dict[str, Any]:
    run = _get_run_for_store(session, store_id=store_id, run_id=run_id)
    store = get_store_or_error(session, store_id)
    rows = session.execute(
        select(InventoryAdviceItem, Product.name, ProductSku.sku_code, ProductSku.sku_name)
        .join(Product, Product.id == InventoryAdviceItem.product_id)
        .join(ProductSku, ProductSku.id == InventoryAdviceItem.sku_id)
        .where(InventoryAdviceItem.run_id == run.id)
        .order_by(InventoryAdviceItem.id.asc())
    ).all()
    response = _run_summary(run, store)
    response["items"] = [
        _item_response(
            row.InventoryAdviceItem,
            product_name=row.name,
            sku_code=row.sku_code,
            sku_name=row.sku_name,
        )
        for row in rows
    ]
    return response


def get_latest_inventory_advice(session: Session, store_id: int) -> dict[str, Any]:
    get_store_or_error(session, store_id)
    run_id = session.scalar(
        select(InventoryAdviceRun.id)
        .where(InventoryAdviceRun.store_id == store_id)
        .order_by(InventoryAdviceRun.id.desc())
        .limit(1)
    )
    if run_id is None:
        raise AppError(404, "INVENTORY_ADVICE_NOT_FOUND", "该店铺尚未生成库存建议")
    return get_inventory_advice_run(session, store_id=store_id, run_id=run_id)


def list_inventory_advice_runs(
    session: Session, *, store_id: int, page: int, page_size: int
) -> tuple[list[dict[str, Any]], int]:
    store = get_store_or_error(session, store_id)
    total = (
        session.scalar(
            select(func.count(InventoryAdviceRun.id)).where(InventoryAdviceRun.store_id == store_id)
        )
        or 0
    )
    runs = session.scalars(
        select(InventoryAdviceRun)
        .where(InventoryAdviceRun.store_id == store_id)
        .order_by(InventoryAdviceRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_run_summary(run, store) for run in runs], int(total)


def _priority(
    *, available_qty: int, warning_threshold: int, outbound_qty: int, restock: int
) -> str:
    if available_qty == 0 and outbound_qty > 0:
        return "critical"
    if available_qty <= warning_threshold:
        return "high"
    if restock > 0:
        return "medium"
    return "low"


def _build_explanation(
    *,
    data_status: str,
    lookback_days: int,
    outbound_qty: int,
    outbound_events: int,
    available_qty: int,
    warning_threshold: int,
    target_stock_qty: int,
    suggested_restock_qty: int,
) -> str:
    if data_status == "insufficient":
        return (
            f"最近 {lookback_days} 天仅有 {outbound_events} 条出库记录，数据不足；"
            f"当前可用库存 {available_qty}，预警阈值 {warning_threshold}，"
            f"建议先补充销量数据并人工复核，最低参考补货量 {suggested_restock_qty}。"
        )
    return (
        f"最近 {lookback_days} 天出库 {outbound_qty} 件（{outbound_events} 次），"
        f"当前可用库存 {available_qty}，按覆盖周期和安全系数计算目标库存 "
        f"{target_stock_qty}，建议补货 {suggested_restock_qty} 件。"
    )


def generate_inventory_advice(
    session: Session,
    *,
    store_id: int,
    payload: InventoryAdviceGenerateRequest,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    store = get_store_or_error(session, store_id)
    if store.status != "active":
        raise AppError(409, "STORE_INACTIVE", "停用店铺不能生成库存建议")
    cutoff = datetime.now(UTC) - timedelta(days=payload.lookback_days)
    movement_stats = (
        select(
            InventoryMovement.sku_id.label("sku_id"),
            func.sum(-InventoryMovement.change_qty).label("outbound_qty"),
            func.count(InventoryMovement.id).label("outbound_events"),
        )
        .where(
            InventoryMovement.movement_type == "outbound",
            InventoryMovement.change_qty < 0,
            InventoryMovement.created_at >= cutoff,
        )
        .group_by(InventoryMovement.sku_id)
        .subquery()
    )
    rows = session.execute(
        select(
            Product,
            ProductSku,
            InventoryItem,
            func.coalesce(movement_stats.c.outbound_qty, 0).label("outbound_qty"),
            func.coalesce(movement_stats.c.outbound_events, 0).label("outbound_events"),
        )
        .join(ProductSku, ProductSku.product_id == Product.id)
        .join(InventoryItem, InventoryItem.sku_id == ProductSku.id)
        .outerjoin(movement_stats, movement_stats.c.sku_id == ProductSku.id)
        .where(
            Product.store_id == store.id,
            Product.status == "active",
            ProductSku.status == "active",
        )
        .order_by(ProductSku.id.asc())
    ).all()

    run = InventoryAdviceRun(
        store_id=store.id,
        rule_version=RULE_VERSION,
        lookback_days=payload.lookback_days,
        coverage_days=payload.coverage_days,
        safety_multiplier=payload.safety_multiplier,
        min_outbound_events=payload.min_outbound_events,
        item_count=0,
        replenish_count=0,
        insufficient_count=0,
        generated_by=actor.id,
    )
    session.add(run)
    session.flush()

    replenish_count = 0
    insufficient_count = 0
    for row in rows:
        inventory = row.InventoryItem
        available_qty = inventory.stock_qty - inventory.locked_qty
        outbound_qty = int(row.outbound_qty)
        outbound_events = int(row.outbound_events)
        data_status = (
            "sufficient" if outbound_events >= payload.min_outbound_events else "insufficient"
        )
        daily_rate = (Decimal(outbound_qty) / Decimal(payload.lookback_days)).quantize(
            Decimal("0.0001")
        )
        demand_target = int(
            (
                daily_rate * Decimal(payload.coverage_days) * payload.safety_multiplier
            ).to_integral_value(rounding=ROUND_CEILING)
        )
        target_stock_qty = max(inventory.warning_threshold + 1, demand_target)
        suggested_restock_qty = max(0, target_stock_qty - available_qty)
        if data_status == "insufficient":
            action = "monitor"
            insufficient_count += 1
        elif suggested_restock_qty > 0:
            action = "replenish"
            replenish_count += 1
        else:
            action = "healthy"
        priority = _priority(
            available_qty=available_qty,
            warning_threshold=inventory.warning_threshold,
            outbound_qty=outbound_qty,
            restock=suggested_restock_qty,
        )
        session.add(
            InventoryAdviceItem(
                run_id=run.id,
                product_id=row.Product.id,
                sku_id=row.ProductSku.id,
                stock_qty=inventory.stock_qty,
                locked_qty=inventory.locked_qty,
                available_qty=available_qty,
                warning_threshold=inventory.warning_threshold,
                outbound_qty=outbound_qty,
                outbound_events=outbound_events,
                daily_outbound_rate=daily_rate,
                target_stock_qty=target_stock_qty,
                suggested_restock_qty=suggested_restock_qty,
                action=action,
                priority=priority,
                data_status=data_status,
                explanation=_build_explanation(
                    data_status=data_status,
                    lookback_days=payload.lookback_days,
                    outbound_qty=outbound_qty,
                    outbound_events=outbound_events,
                    available_qty=available_qty,
                    warning_threshold=inventory.warning_threshold,
                    target_stock_qty=target_stock_qty,
                    suggested_restock_qty=suggested_restock_qty,
                ),
            )
        )

    run.item_count = len(rows)
    run.replenish_count = replenish_count
    run.insufficient_count = insufficient_count
    if not rows:
        run.message = "该店铺没有有效商品和 SKU，暂时无法生成库存建议"
    elif insufficient_count == len(rows):
        run.message = "全部 SKU 的出库数据不足，建议补充销量数据后重新生成"
    elif insufficient_count:
        run.message = f"有 {insufficient_count} 个 SKU 的出库数据不足，请人工复核"
    else:
        run.message = "已根据当前库存和近期出库数据生成规则建议"

    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="inventory_advice.generate",
        target_type="inventory_advice_run",
        target_id=run.id,
        request_id=request_id,
        detail={
            "store_id": store.id,
            "rule_version": RULE_VERSION,
            "item_count": run.item_count,
            "replenish_count": replenish_count,
            "insufficient_count": insufficient_count,
        },
    )
    session.commit()
    return get_inventory_advice_run(session, store_id=store.id, run_id=run.id)
