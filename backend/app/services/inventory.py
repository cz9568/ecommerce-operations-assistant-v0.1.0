from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.api.schemas.inventory import (
    InventoryAdjustmentCreate,
    InventoryConfigUpdate,
)
from backend.app.errors import AppError
from backend.app.models.entities import (
    InventoryItem,
    InventoryMovement,
    Product,
    ProductSku,
    Store,
    User,
)
from backend.app.services.audit import add_audit_log
from backend.app.services.products import get_product_or_error
from backend.app.services.stores import get_store_or_error


def _get_sku_for_product(session: Session, *, product_id: int, sku_id: int) -> ProductSku:
    get_product_or_error(session, product_id)
    sku = session.scalar(
        select(ProductSku).where(
            ProductSku.id == sku_id,
            ProductSku.product_id == product_id,
        )
    )
    if sku is None:
        raise AppError(404, "SKU_NOT_FOUND", "SKU 不存在或不属于该商品")
    return sku


def _get_inventory_for_update(session: Session, sku_id: int) -> InventoryItem:
    inventory = session.scalar(
        select(InventoryItem).where(InventoryItem.sku_id == sku_id).with_for_update()
    )
    if inventory is None:
        raise AppError(409, "INVENTORY_NOT_INITIALIZED", "SKU 库存记录尚未初始化")
    return inventory


def _check_version(inventory: InventoryItem, expected_version: int) -> None:
    if inventory.version_no != expected_version:
        raise AppError(
            409,
            "INVENTORY_VERSION_CONFLICT",
            "库存已被其他操作更新，请刷新后重试",
            details={"current_version": inventory.version_no},
        )


def _inventory_response(
    inventory: InventoryItem,
    *,
    sku: ProductSku,
    product: Product,
    store: Store,
) -> dict[str, Any]:
    available_qty = inventory.stock_qty - inventory.locked_qty
    return {
        "id": inventory.id,
        "store_id": store.id,
        "store_name": store.store_name,
        "product_id": product.id,
        "product_name": product.name,
        "sku_id": sku.id,
        "sku_code": sku.sku_code,
        "sku_name": sku.sku_name,
        "sku_status": sku.status,
        "stock_qty": inventory.stock_qty,
        "locked_qty": inventory.locked_qty,
        "available_qty": available_qty,
        "warning_threshold": inventory.warning_threshold,
        "is_low_stock": available_qty <= inventory.warning_threshold,
        "location_text": inventory.location_text,
        "version_no": inventory.version_no,
        "updated_at": inventory.updated_at,
    }


def _movement_response(movement: InventoryMovement) -> dict[str, Any]:
    return {
        "id": movement.id,
        "sku_id": movement.sku_id,
        "movement_type": movement.movement_type,
        "quantity_type": ("locked" if movement.movement_type in {"lock", "unlock"} else "stock"),
        "change_qty": movement.change_qty,
        "before_qty": movement.before_qty,
        "after_qty": movement.after_qty,
        "reason_text": movement.reason_text,
        "reference_type": movement.reference_type,
        "reference_id": movement.reference_id,
        "created_by": movement.created_by,
        "created_at": movement.created_at,
    }


def _inventory_query(filters: list[Any], *, only_low_stock: bool):
    statement = (
        select(InventoryItem, ProductSku, Product, Store)
        .join(ProductSku, ProductSku.id == InventoryItem.sku_id)
        .join(Product, Product.id == ProductSku.product_id)
        .join(Store, Store.id == Product.store_id)
        .where(*filters)
    )
    if only_low_stock:
        statement = statement.where(
            Store.status == "active",
            Product.status == "active",
            InventoryItem.stock_qty - InventoryItem.locked_qty <= InventoryItem.warning_threshold,
        )
    return statement


def list_inventory(
    session: Session,
    *,
    page: int,
    page_size: int,
    store_id: int | None,
    product_id: int | None,
    sku_status: str | None,
    query: str | None,
    only_low_stock: bool,
) -> tuple[list[dict[str, Any]], int]:
    filters = []
    if store_id is not None:
        filters.append(Store.id == store_id)
    if product_id is not None:
        filters.append(Product.id == product_id)
    if sku_status:
        filters.append(ProductSku.status == sku_status)
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                Product.name.like(pattern),
                ProductSku.sku_code.like(pattern),
                ProductSku.sku_name.like(pattern),
            )
        )
    base = _inventory_query(filters, only_low_stock=only_low_stock)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(
        base.order_by(InventoryItem.id.asc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return (
        [
            _inventory_response(
                row.InventoryItem,
                sku=row.ProductSku,
                product=row.Product,
                store=row.Store,
            )
            for row in rows
        ],
        int(total),
    )


def get_inventory_detail(session: Session, *, product_id: int, sku_id: int) -> dict[str, Any]:
    sku = _get_sku_for_product(session, product_id=product_id, sku_id=sku_id)
    product = get_product_or_error(session, product_id)
    store = get_store_or_error(session, product.store_id)
    inventory = session.scalar(select(InventoryItem).where(InventoryItem.sku_id == sku.id))
    if inventory is None:
        raise AppError(404, "INVENTORY_NOT_FOUND", "库存记录不存在")
    return _inventory_response(inventory, sku=sku, product=product, store=store)


def update_inventory_config(
    session: Session,
    *,
    product_id: int,
    sku_id: int,
    payload: InventoryConfigUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    sku = _get_sku_for_product(session, product_id=product_id, sku_id=sku_id)
    product = get_product_or_error(session, product_id)
    store = get_store_or_error(session, product.store_id)
    inventory = _get_inventory_for_update(session, sku.id)
    _check_version(inventory, payload.expected_version)
    data = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    for field_name, value in data.items():
        setattr(inventory, field_name, value)
    inventory.version_no += 1
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="inventory.config_update",
        target_type="inventory_item",
        target_id=inventory.id,
        request_id=request_id,
        detail={"product_id": product.id, "sku_id": sku.id, "changed_fields": sorted(data)},
    )
    session.commit()
    session.refresh(inventory)
    return _inventory_response(inventory, sku=sku, product=product, store=store)


def adjust_inventory(
    session: Session,
    *,
    product_id: int,
    sku_id: int,
    payload: InventoryAdjustmentCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    sku = _get_sku_for_product(session, product_id=product_id, sku_id=sku_id)
    product = get_product_or_error(session, product_id)
    store = get_store_or_error(session, product.store_id)
    inventory = _get_inventory_for_update(session, sku.id)
    _check_version(inventory, payload.expected_version)

    increases_quantity = payload.change_qty > 0
    if increases_quantity and (sku.status != "active" or product.status == "inactive"):
        raise AppError(409, "INVENTORY_TARGET_INACTIVE", "停用商品或 SKU 不能增加或锁定库存")
    if increases_quantity and store.status != "active":
        raise AppError(409, "STORE_INACTIVE", "停用店铺不能增加或锁定库存")

    adjusts_locked = payload.movement_type in {"lock", "unlock"}
    before_qty = inventory.locked_qty if adjusts_locked else inventory.stock_qty
    after_qty = before_qty + payload.change_qty
    if after_qty < 0:
        raise AppError(409, "NEGATIVE_INVENTORY_NOT_ALLOWED", "库存或锁定数量不能为负数")
    resulting_stock = inventory.stock_qty if adjusts_locked else after_qty
    resulting_locked = after_qty if adjusts_locked else inventory.locked_qty
    if resulting_locked > resulting_stock:
        raise AppError(409, "LOCKED_STOCK_EXCEEDS_TOTAL", "锁定数量不能超过总库存")

    if adjusts_locked:
        inventory.locked_qty = after_qty
    else:
        inventory.stock_qty = after_qty
    inventory.version_no += 1
    movement = InventoryMovement(
        sku_id=sku.id,
        movement_type=payload.movement_type,
        change_qty=payload.change_qty,
        before_qty=before_qty,
        after_qty=after_qty,
        reason_text=payload.reason_text,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        created_by=actor.id,
    )
    session.add(movement)
    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="inventory.adjust",
        target_type="inventory_item",
        target_id=inventory.id,
        request_id=request_id,
        detail={
            "product_id": product.id,
            "sku_id": sku.id,
            "movement_id": movement.id,
            "movement_type": movement.movement_type,
            "change_qty": movement.change_qty,
            "before_qty": movement.before_qty,
            "after_qty": movement.after_qty,
        },
    )
    session.commit()
    session.refresh(inventory)
    session.refresh(movement)
    return {
        "inventory": _inventory_response(inventory, sku=sku, product=product, store=store),
        "movement": _movement_response(movement),
    }


def list_inventory_movements(
    session: Session,
    *,
    product_id: int,
    sku_id: int,
    page: int,
    page_size: int,
    movement_type: str | None,
) -> tuple[list[dict[str, Any]], int]:
    sku = _get_sku_for_product(session, product_id=product_id, sku_id=sku_id)
    filters = [InventoryMovement.sku_id == sku.id]
    if movement_type:
        filters.append(InventoryMovement.movement_type == movement_type)
    total = session.scalar(select(func.count(InventoryMovement.id)).where(*filters)) or 0
    movements = session.scalars(
        select(InventoryMovement)
        .where(*filters)
        .order_by(InventoryMovement.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_movement_response(movement) for movement in movements], int(total)
