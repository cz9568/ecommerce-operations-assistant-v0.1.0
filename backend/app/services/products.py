from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.schemas.products import (
    ProductCreate,
    ProductMappingCreate,
    ProductMappingUpdate,
    ProductStatusUpdate,
    ProductUpdate,
)
from backend.app.errors import AppError
from backend.app.models.entities import (
    PlatformProductMapping,
    Product,
    ProductDiagnosis,
    ReviewReport,
    Store,
    User,
)
from backend.app.services.audit import add_audit_log
from backend.app.services.stores import get_store_or_error


def get_product_or_error(session: Session, product_id: int) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise AppError(404, "PRODUCT_NOT_FOUND", "商品不存在或无权访问")
    return product


def _diagnosis_subquery():
    return (
        select(
            ProductDiagnosis.product_id.label("product_id"),
            func.max(ProductDiagnosis.created_at).label("last_diagnosis_at"),
        )
        .group_by(ProductDiagnosis.product_id)
        .subquery()
    )


def _review_subquery():
    return (
        select(
            ReviewReport.product_id.label("product_id"),
            func.max(ReviewReport.created_at).label("last_review_at"),
        )
        .group_by(ReviewReport.product_id)
        .subquery()
    )


def _mapping_count_subquery():
    return (
        select(
            PlatformProductMapping.product_id.label("product_id"),
            func.count(PlatformProductMapping.id).label("mapping_count"),
        )
        .group_by(PlatformProductMapping.product_id)
        .subquery()
    )


def _product_response(
    product: Product,
    *,
    store_name: str,
    mapping_count: int,
    last_diagnosis_at: Any | None,
    last_review_at: Any | None,
) -> dict[str, Any]:
    return {
        "id": product.id,
        "store_id": product.store_id,
        "store_name": store_name,
        "name": product.name,
        "platform": product.platform,
        "category": product.category,
        "price": product.price,
        "cost": product.cost,
        "target_audience": product.target_audience,
        "selling_points": product.selling_points,
        "product_url": product.product_url,
        "images": product.images_json or [],
        "status": product.status,
        "mapping_count": mapping_count,
        "last_diagnosis_at": last_diagnosis_at,
        "last_review_at": last_review_at,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }


def list_products(
    session: Session,
    *,
    page: int,
    page_size: int,
    store_id: int | None,
    platform: str | None,
    status: str | None,
    category: str | None,
    query: str | None,
) -> tuple[list[dict[str, Any]], int]:
    filters = []
    if store_id is not None:
        filters.append(Product.store_id == store_id)
    if platform:
        filters.append(Product.platform == platform)
    if status:
        filters.append(Product.status == status)
    if category:
        filters.append(Product.category == category.strip())
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(or_(Product.name.like(pattern), Product.category.like(pattern)))

    total = session.scalar(select(func.count(Product.id)).where(*filters)) or 0
    diagnoses = _diagnosis_subquery()
    reviews = _review_subquery()
    mappings = _mapping_count_subquery()
    rows = session.execute(
        select(
            Product,
            Store.store_name,
            func.coalesce(mappings.c.mapping_count, 0).label("mapping_count"),
            diagnoses.c.last_diagnosis_at,
            reviews.c.last_review_at,
        )
        .join(Store, Store.id == Product.store_id)
        .outerjoin(mappings, mappings.c.product_id == Product.id)
        .outerjoin(diagnoses, diagnoses.c.product_id == Product.id)
        .outerjoin(reviews, reviews.c.product_id == Product.id)
        .where(*filters)
        .order_by(Product.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return (
        [
            _product_response(
                row.Product,
                store_name=row.store_name,
                mapping_count=int(row.mapping_count),
                last_diagnosis_at=row.last_diagnosis_at,
                last_review_at=row.last_review_at,
            )
            for row in rows
        ],
        int(total),
    )


def get_product_detail(session: Session, product_id: int) -> dict[str, Any]:
    product = get_product_or_error(session, product_id)
    store = get_store_or_error(session, product.store_id)
    mapping_count = (
        session.scalar(
            select(func.count(PlatformProductMapping.id)).where(
                PlatformProductMapping.product_id == product.id
            )
        )
        or 0
    )
    last_diagnosis_at = session.scalar(
        select(func.max(ProductDiagnosis.created_at)).where(
            ProductDiagnosis.product_id == product.id
        )
    )
    last_review_at = session.scalar(
        select(func.max(ReviewReport.created_at)).where(ReviewReport.product_id == product.id)
    )
    return _product_response(
        product,
        store_name=store.store_name,
        mapping_count=int(mapping_count),
        last_diagnosis_at=last_diagnosis_at,
        last_review_at=last_review_at,
    )


def create_product(
    session: Session,
    *,
    payload: ProductCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    store = get_store_or_error(session, payload.store_id)
    if store.status != "active":
        raise AppError(409, "STORE_INACTIVE", "停用店铺不能新增商品")
    product = Product(
        store_id=store.id,
        name=payload.name,
        platform=store.platform,
        category=payload.category,
        price=payload.price,
        cost=payload.cost,
        target_audience=payload.target_audience,
        selling_points=payload.selling_points,
        product_url=payload.product_url,
        images_json=payload.images,
        status=payload.status,
    )
    session.add(product)
    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="product.create",
        target_type="product",
        target_id=product.id,
        request_id=request_id,
        detail={"store_id": store.id, "platform": product.platform, "status": product.status},
    )
    session.commit()
    session.refresh(product)
    return get_product_detail(session, product.id)


def update_product(
    session: Session,
    *,
    product_id: int,
    payload: ProductUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    product = get_product_or_error(session, product_id)
    data = payload.model_dump(exclude_unset=True)
    if "images" in data:
        product.images_json = data.pop("images")
    image_fields = {"images"} if "images" in payload.model_fields_set else set()
    changed_fields = sorted(data.keys() | image_fields)
    for field_name, value in data.items():
        setattr(product, field_name, value)
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="product.update",
        target_type="product",
        target_id=product.id,
        request_id=request_id,
        detail={"store_id": product.store_id, "changed_fields": changed_fields},
    )
    session.commit()
    session.refresh(product)
    return get_product_detail(session, product.id)


def change_product_status(
    session: Session,
    *,
    product_id: int,
    payload: ProductStatusUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    product = get_product_or_error(session, product_id)
    if payload.status == "active":
        store = get_store_or_error(session, product.store_id)
        if store.status != "active":
            raise AppError(409, "STORE_INACTIVE", "停用店铺中的商品不能启用")
    old_status = product.status
    product.status = payload.status
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="product.status_change",
        target_type="product",
        target_id=product.id,
        request_id=request_id,
        detail={"old_status": old_status, "new_status": product.status},
    )
    session.commit()
    session.refresh(product)
    return get_product_detail(session, product.id)


def archive_product(
    session: Session,
    *,
    product_id: int,
    actor: User,
    request_id: str | None,
) -> None:
    product = get_product_or_error(session, product_id)
    old_status = product.status
    product.status = "inactive"
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="product.archive",
        target_type="product",
        target_id=product.id,
        request_id=request_id,
        detail={"old_status": old_status, "new_status": "inactive"},
    )
    session.commit()


def _mapping_response(mapping: PlatformProductMapping) -> dict[str, Any]:
    return {
        "id": mapping.id,
        "store_id": mapping.store_id,
        "product_id": mapping.product_id,
        "platform": mapping.platform,
        "platform_product_id": mapping.platform_product_id,
        "platform_sku_id": mapping.platform_sku_id,
        "mapping_status": mapping.mapping_status,
        "created_at": mapping.created_at,
        "updated_at": mapping.updated_at,
    }


def _get_mapping_for_product(
    session: Session, *, product_id: int, mapping_id: int
) -> PlatformProductMapping:
    get_product_or_error(session, product_id)
    mapping = session.scalar(
        select(PlatformProductMapping).where(
            PlatformProductMapping.id == mapping_id,
            PlatformProductMapping.product_id == product_id,
        )
    )
    if mapping is None:
        raise AppError(404, "PRODUCT_MAPPING_NOT_FOUND", "平台商品映射不存在或不属于该商品")
    return mapping


def _ensure_mapping_available(
    session: Session,
    *,
    store_id: int,
    platform: str,
    platform_product_id: str,
    platform_sku_id: str,
    excluding_mapping_id: int | None = None,
) -> None:
    statement = select(PlatformProductMapping.id).where(
        PlatformProductMapping.store_id == store_id,
        PlatformProductMapping.platform == platform,
        PlatformProductMapping.platform_product_id == platform_product_id,
        PlatformProductMapping.platform_sku_id == platform_sku_id,
    )
    if excluding_mapping_id is not None:
        statement = statement.where(PlatformProductMapping.id != excluding_mapping_id)
    if session.scalar(statement) is not None:
        raise AppError(409, "PLATFORM_MAPPING_EXISTS", "该店铺的平台商品映射已绑定其他商品")


def list_product_mappings(session: Session, product_id: int) -> list[dict[str, Any]]:
    get_product_or_error(session, product_id)
    mappings = session.scalars(
        select(PlatformProductMapping)
        .where(PlatformProductMapping.product_id == product_id)
        .order_by(PlatformProductMapping.id.asc())
    ).all()
    return [_mapping_response(mapping) for mapping in mappings]


def create_product_mapping(
    session: Session,
    *,
    product_id: int,
    payload: ProductMappingCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    product = get_product_or_error(session, product_id)
    _ensure_mapping_available(
        session,
        store_id=product.store_id,
        platform=product.platform,
        platform_product_id=payload.platform_product_id,
        platform_sku_id=payload.platform_sku_id,
    )
    mapping = PlatformProductMapping(
        store_id=product.store_id,
        product_id=product.id,
        platform=product.platform,
        platform_product_id=payload.platform_product_id,
        platform_sku_id=payload.platform_sku_id,
        mapping_status=payload.mapping_status,
        raw_payload_json=None,
    )
    session.add(mapping)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "PLATFORM_MAPPING_EXISTS", "该店铺的平台商品映射已存在") from exc
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="product_mapping.create",
        target_type="platform_product_mapping",
        target_id=mapping.id,
        request_id=request_id,
        detail={"store_id": product.store_id, "product_id": product.id},
    )
    session.commit()
    session.refresh(mapping)
    return _mapping_response(mapping)


def update_product_mapping(
    session: Session,
    *,
    product_id: int,
    mapping_id: int,
    payload: ProductMappingUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    mapping = _get_mapping_for_product(session, product_id=product_id, mapping_id=mapping_id)
    data = payload.model_dump(exclude_unset=True)
    resulting_product_id = data.get("platform_product_id", mapping.platform_product_id)
    resulting_sku_id = data.get("platform_sku_id", mapping.platform_sku_id)
    _ensure_mapping_available(
        session,
        store_id=mapping.store_id,
        platform=mapping.platform,
        platform_product_id=resulting_product_id,
        platform_sku_id=resulting_sku_id,
        excluding_mapping_id=mapping.id,
    )
    for field_name, value in data.items():
        setattr(mapping, field_name, value)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "PLATFORM_MAPPING_EXISTS", "该店铺的平台商品映射已存在") from exc
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="product_mapping.update",
        target_type="platform_product_mapping",
        target_id=mapping.id,
        request_id=request_id,
        detail={"store_id": mapping.store_id, "product_id": mapping.product_id},
    )
    session.commit()
    session.refresh(mapping)
    return _mapping_response(mapping)


def delete_product_mapping(
    session: Session,
    *,
    product_id: int,
    mapping_id: int,
    actor: User,
    request_id: str | None,
) -> None:
    mapping = _get_mapping_for_product(session, product_id=product_id, mapping_id=mapping_id)
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="product_mapping.delete",
        target_type="platform_product_mapping",
        target_id=mapping.id,
        request_id=request_id,
        detail={"store_id": mapping.store_id, "product_id": mapping.product_id},
    )
    session.execute(delete(PlatformProductMapping).where(PlatformProductMapping.id == mapping.id))
    session.commit()
