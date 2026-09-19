from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.schemas.stores import StoreCreate, StoreUpdate
from backend.app.errors import AppError
from backend.app.models.entities import (
    InventoryItem,
    PlatformAccount,
    Product,
    ProductSku,
    Store,
    User,
)
from backend.app.services.audit import add_audit_log


def get_store_or_error(session: Session, store_id: int) -> Store:
    store = session.get(Store, store_id)
    if store is None:
        raise AppError(404, "STORE_NOT_FOUND", "店铺不存在")
    return store


def _get_active_owner(session: Session, owner_user_id: int | None) -> User | None:
    if owner_user_id is None:
        return None
    owner = session.get(User, owner_user_id)
    if owner is None:
        raise AppError(422, "STORE_OWNER_NOT_FOUND", "店铺负责人不存在")
    if owner.status != "active":
        raise AppError(409, "STORE_OWNER_INACTIVE", "店铺负责人必须是有效用户")
    return owner


def _ensure_external_id_available(
    session: Session,
    *,
    platform: str,
    external_store_id: str | None,
    excluding_store_id: int | None = None,
) -> None:
    if external_store_id is None:
        return
    statement = select(Store.id).where(
        Store.platform == platform,
        Store.external_store_id == external_store_id,
    )
    if excluding_store_id is not None:
        statement = statement.where(Store.id != excluding_store_id)
    if session.scalar(statement) is not None:
        raise AppError(409, "STORE_EXTERNAL_ID_EXISTS", "该平台店铺编号已存在")


def _product_count_subquery():
    return (
        select(Product.store_id.label("store_id"), func.count(Product.id).label("product_count"))
        .group_by(Product.store_id)
        .subquery()
    )


def _low_stock_count_subquery():
    return (
        select(
            Product.store_id.label("store_id"),
            func.count(InventoryItem.id).label("low_stock_count"),
        )
        .join(ProductSku, ProductSku.product_id == Product.id)
        .join(InventoryItem, InventoryItem.sku_id == ProductSku.id)
        .where(
            Product.status == "active",
            ProductSku.status == "active",
            InventoryItem.stock_qty - InventoryItem.locked_qty <= InventoryItem.warning_threshold,
        )
        .group_by(Product.store_id)
        .subquery()
    )


def _store_response(
    store: Store,
    *,
    product_count: int,
    low_stock_count: int,
    owner_name: str | None,
) -> dict[str, Any]:
    return {
        "id": store.id,
        "store_name": store.store_name,
        "platform": store.platform,
        "external_store_id": store.external_store_id,
        "owner_user_id": store.owner_user_id,
        "owner_name": owner_name,
        "status": store.status,
        "remark": store.remark,
        "product_count": product_count,
        "low_stock_count": low_stock_count,
        "created_at": store.created_at,
        "updated_at": store.updated_at,
    }


def list_stores(
    session: Session,
    *,
    page: int,
    page_size: int,
    platform: str | None,
    status: str | None,
    owner_user_id: int | None,
    query: str | None,
) -> tuple[list[dict[str, Any]], int]:
    filters = []
    if platform:
        filters.append(Store.platform == platform)
    if status:
        filters.append(Store.status == status)
    if owner_user_id is not None:
        filters.append(Store.owner_user_id == owner_user_id)
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(or_(Store.store_name.like(pattern), Store.external_store_id.like(pattern)))

    total = session.scalar(select(func.count(Store.id)).where(*filters)) or 0
    products = _product_count_subquery()
    low_stock = _low_stock_count_subquery()
    rows = session.execute(
        select(
            Store,
            User.display_name.label("current_owner_name"),
            func.coalesce(products.c.product_count, 0).label("product_count"),
            func.coalesce(low_stock.c.low_stock_count, 0).label("low_stock_count"),
        )
        .outerjoin(User, User.id == Store.owner_user_id)
        .outerjoin(products, products.c.store_id == Store.id)
        .outerjoin(low_stock, low_stock.c.store_id == Store.id)
        .where(*filters)
        .order_by(Store.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        _store_response(
            row.Store,
            product_count=int(row.product_count),
            low_stock_count=int(row.low_stock_count),
            owner_name=row.current_owner_name or row.Store.owner_name,
        )
        for row in rows
    ]
    return items, int(total)


def get_store_detail(session: Session, store_id: int) -> dict[str, Any]:
    store = get_store_or_error(session, store_id)
    owner = session.get(User, store.owner_user_id) if store.owner_user_id is not None else None
    product_count = (
        session.scalar(select(func.count(Product.id)).where(Product.store_id == store.id)) or 0
    )
    low_stock_count = (
        session.scalar(
            select(func.count(InventoryItem.id))
            .join(ProductSku, ProductSku.id == InventoryItem.sku_id)
            .join(Product, Product.id == ProductSku.product_id)
            .where(
                Product.store_id == store.id,
                Product.status == "active",
                ProductSku.status == "active",
                InventoryItem.stock_qty - InventoryItem.locked_qty
                <= InventoryItem.warning_threshold,
            )
        )
        or 0
    )
    return _store_response(
        store,
        product_count=int(product_count),
        low_stock_count=int(low_stock_count),
        owner_name=owner.display_name if owner else store.owner_name,
    )


def get_store_summary(session: Session, store_id: int) -> dict[str, int]:
    get_store_or_error(session, store_id)
    product_count = (
        session.scalar(select(func.count(Product.id)).where(Product.store_id == store_id)) or 0
    )
    sku_count = (
        session.scalar(
            select(func.count(ProductSku.id))
            .join(Product, Product.id == ProductSku.product_id)
            .where(Product.store_id == store_id)
        )
        or 0
    )
    low_stock_count = (
        session.scalar(
            select(func.count(InventoryItem.id))
            .join(ProductSku, ProductSku.id == InventoryItem.sku_id)
            .join(Product, Product.id == ProductSku.product_id)
            .where(
                Product.store_id == store_id,
                Product.status == "active",
                ProductSku.status == "active",
                InventoryItem.stock_qty - InventoryItem.locked_qty
                <= InventoryItem.warning_threshold,
            )
        )
        or 0
    )
    platform_account_count = (
        session.scalar(
            select(func.count(PlatformAccount.id)).where(PlatformAccount.store_id == store_id)
        )
        or 0
    )
    authorized_account_count = (
        session.scalar(
            select(func.count(PlatformAccount.id)).where(
                PlatformAccount.store_id == store_id,
                PlatformAccount.auth_status == "authorized",
            )
        )
        or 0
    )
    return {
        "store_id": store_id,
        "product_count": int(product_count),
        "sku_count": int(sku_count),
        "low_stock_count": int(low_stock_count),
        "platform_account_count": int(platform_account_count),
        "authorized_account_count": int(authorized_account_count),
    }


def create_store(
    session: Session,
    *,
    payload: StoreCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    owner = _get_active_owner(session, payload.owner_user_id)
    _ensure_external_id_available(
        session,
        platform=payload.platform,
        external_store_id=payload.external_store_id,
    )
    store = Store(
        store_name=payload.store_name,
        platform=payload.platform,
        external_store_id=payload.external_store_id,
        owner_user_id=payload.owner_user_id,
        owner_name=owner.display_name if owner else None,
        status=payload.status,
        remark=payload.remark,
    )
    session.add(store)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "STORE_EXTERNAL_ID_EXISTS", "该平台店铺编号已存在") from exc

    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="store.create",
        target_type="store",
        target_id=store.id,
        request_id=request_id,
        detail={"platform": store.platform, "status": store.status},
    )
    session.commit()
    session.refresh(store)
    return get_store_detail(session, store.id)


def update_store(
    session: Session,
    *,
    store_id: int,
    payload: StoreUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    store = get_store_or_error(session, store_id)
    data = payload.model_dump(exclude_unset=True)
    resulting_platform = data.get("platform", store.platform)
    resulting_external_id = data.get("external_store_id", store.external_store_id)

    if resulting_platform != store.platform:
        has_dependencies = session.scalar(
            select(PlatformAccount.id).where(PlatformAccount.store_id == store.id).limit(1)
        ) or session.scalar(select(Product.id).where(Product.store_id == store.id).limit(1))
        if has_dependencies is not None:
            raise AppError(
                409,
                "STORE_PLATFORM_IN_USE",
                "店铺已有平台账号或商品，不能修改所属平台",
            )

    _ensure_external_id_available(
        session,
        platform=resulting_platform,
        external_store_id=resulting_external_id,
        excluding_store_id=store.id,
    )
    if "owner_user_id" in data:
        owner = _get_active_owner(session, data["owner_user_id"])
        store.owner_name = owner.display_name if owner else None

    old_status = store.status
    old_platform = store.platform
    for field_name, value in data.items():
        setattr(store, field_name, value)

    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "STORE_EXTERNAL_ID_EXISTS", "该平台店铺编号已存在") from exc

    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="store.update",
        target_type="store",
        target_id=store.id,
        request_id=request_id,
        detail={
            "old_status": old_status,
            "new_status": store.status,
            "old_platform": old_platform,
            "new_platform": store.platform,
        },
    )
    session.commit()
    session.refresh(store)
    return get_store_detail(session, store.id)
