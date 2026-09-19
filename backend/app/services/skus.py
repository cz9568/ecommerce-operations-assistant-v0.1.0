from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.schemas.skus import SkuCreate, SkuStatusUpdate, SkuUpdate
from backend.app.errors import AppError
from backend.app.models.entities import InventoryItem, Product, ProductSku, User
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


def _ensure_sku_code_available(
    session: Session,
    *,
    product_id: int,
    sku_code: str,
    excluding_sku_id: int | None = None,
) -> None:
    statement = select(ProductSku.id).where(
        ProductSku.product_id == product_id,
        func.lower(ProductSku.sku_code) == sku_code.lower(),
    )
    if excluding_sku_id is not None:
        statement = statement.where(ProductSku.id != excluding_sku_id)
    if session.scalar(statement) is not None:
        raise AppError(409, "SKU_CODE_EXISTS", "该商品下的 SKU 编码已存在")


def _ensure_product_allows_active_sku(session: Session, product: Product) -> None:
    if product.status == "inactive":
        raise AppError(409, "PRODUCT_INACTIVE", "停用商品不能新增或启用 SKU")
    store = get_store_or_error(session, product.store_id)
    if store.status != "active":
        raise AppError(409, "STORE_INACTIVE", "停用店铺不能新增或启用 SKU")


def _sku_response(sku: ProductSku, product: Product) -> dict[str, Any]:
    return {
        "id": sku.id,
        "product_id": sku.product_id,
        "product_name": product.name,
        "store_id": product.store_id,
        "sku_code": sku.sku_code,
        "sku_name": sku.sku_name,
        "specs": sku.spec_json or {},
        "price": sku.price,
        "cost": sku.cost,
        "status": sku.status,
        "platform_sku_id": sku.platform_sku_id,
        "created_at": sku.created_at,
        "updated_at": sku.updated_at,
    }


def list_skus(
    session: Session,
    *,
    product_id: int,
    page: int,
    page_size: int,
    status: str | None,
    query: str | None,
) -> tuple[list[dict[str, Any]], int]:
    product = get_product_or_error(session, product_id)
    filters = [ProductSku.product_id == product_id]
    if status:
        filters.append(ProductSku.status == status)
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                ProductSku.sku_code.like(pattern),
                ProductSku.sku_name.like(pattern),
                ProductSku.platform_sku_id.like(pattern),
            )
        )
    total = session.scalar(select(func.count(ProductSku.id)).where(*filters)) or 0
    skus = session.scalars(
        select(ProductSku)
        .where(*filters)
        .order_by(ProductSku.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_sku_response(sku, product) for sku in skus], int(total)


def get_sku_detail(session: Session, *, product_id: int, sku_id: int) -> dict[str, Any]:
    sku = _get_sku_for_product(session, product_id=product_id, sku_id=sku_id)
    product = get_product_or_error(session, product_id)
    return _sku_response(sku, product)


def create_sku(
    session: Session,
    *,
    product_id: int,
    payload: SkuCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    product = get_product_or_error(session, product_id)
    _ensure_product_allows_active_sku(session, product)
    _ensure_sku_code_available(session, product_id=product.id, sku_code=payload.sku_code)
    sku = ProductSku(
        product_id=product.id,
        sku_code=payload.sku_code,
        sku_name=payload.sku_name,
        spec_json=payload.specs,
        price=payload.price,
        cost=payload.cost,
        status=payload.status,
        platform_sku_id=payload.platform_sku_id,
    )
    session.add(sku)
    try:
        session.flush()
        session.add(
            InventoryItem(
                sku_id=sku.id,
                stock_qty=0,
                locked_qty=0,
                warning_threshold=0,
                version_no=1,
            )
        )
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "SKU_CODE_EXISTS", "该商品下的 SKU 编码已存在") from exc
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="sku.create",
        target_type="product_sku",
        target_id=sku.id,
        request_id=request_id,
        detail={"store_id": product.store_id, "product_id": product.id, "status": sku.status},
    )
    session.commit()
    session.refresh(sku)
    return _sku_response(sku, product)


def update_sku(
    session: Session,
    *,
    product_id: int,
    sku_id: int,
    payload: SkuUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    sku = _get_sku_for_product(session, product_id=product_id, sku_id=sku_id)
    product = get_product_or_error(session, product_id)
    data = payload.model_dump(exclude_unset=True)
    if "sku_code" in data:
        _ensure_sku_code_available(
            session,
            product_id=product_id,
            sku_code=data["sku_code"],
            excluding_sku_id=sku.id,
        )
    if "specs" in data:
        sku.spec_json = data.pop("specs")
    spec_fields = {"specs"} if "specs" in payload.model_fields_set else set()
    changed_fields = sorted(data.keys() | spec_fields)
    for field_name, value in data.items():
        setattr(sku, field_name, value)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "SKU_CODE_EXISTS", "该商品下的 SKU 编码已存在") from exc
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="sku.update",
        target_type="product_sku",
        target_id=sku.id,
        request_id=request_id,
        detail={"product_id": product.id, "changed_fields": changed_fields},
    )
    session.commit()
    session.refresh(sku)
    return _sku_response(sku, product)


def change_sku_status(
    session: Session,
    *,
    product_id: int,
    sku_id: int,
    payload: SkuStatusUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    sku = _get_sku_for_product(session, product_id=product_id, sku_id=sku_id)
    product = get_product_or_error(session, product_id)
    if payload.status == "active":
        _ensure_product_allows_active_sku(session, product)
    old_status = sku.status
    sku.status = payload.status
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="sku.status_change",
        target_type="product_sku",
        target_id=sku.id,
        request_id=request_id,
        detail={"product_id": product.id, "old_status": old_status, "new_status": sku.status},
    )
    session.commit()
    session.refresh(sku)
    return _sku_response(sku, product)
