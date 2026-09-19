from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.products import (
    ProductCreate,
    ProductMappingCreate,
    ProductMappingResponse,
    ProductMappingUpdate,
    ProductResponse,
    ProductStatus,
    ProductStatusUpdate,
    ProductUpdate,
)
from backend.app.api.schemas.stores import StorePlatform
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.products import (
    archive_product,
    change_product_status,
    create_product,
    create_product_mapping,
    delete_product_mapping,
    get_product_detail,
    list_product_mappings,
    list_products,
    update_product,
    update_product_mapping,
)

router = APIRouter(prefix="/products", tags=["商品管理"])
ProductWriter = Annotated[User, Depends(require_permissions(Permission.PRODUCT_WRITE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=Page[ProductResponse])
def get_products(
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    store_id: Annotated[int | None, Query(ge=1)] = None,
    platform: StorePlatform | None = None,
    product_status: Annotated[ProductStatus | None, Query(alias="status")] = None,
    category: Annotated[str | None, Query(max_length=120)] = None,
    query: Annotated[str | None, Query(alias="q", max_length=255)] = None,
) -> Page[ProductResponse]:
    del current_user
    products, total = list_products(
        session,
        page=page,
        page_size=page_size,
        store_id=store_id,
        platform=platform,
        status=product_status,
        category=category,
        query=query,
    )
    return Page(items=products, page=page, page_size=page_size, total=total)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def post_product(
    payload: ProductCreate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return create_product(
        session,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_product_detail(session, product_id)


@router.patch("/{product_id}", response_model=ProductResponse)
def patch_product(
    product_id: int,
    payload: ProductUpdate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return update_product(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.patch("/{product_id}/status", response_model=ProductResponse)
def patch_product_status(
    product_id: int,
    payload: ProductStatusUpdate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return change_product_status(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> Response:
    archive_product(
        session,
        product_id=product_id,
        actor=writer,
        request_id=request.state.request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{product_id}/mappings",
    response_model=list[ProductMappingResponse],
)
def get_product_mappings(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[dict]:
    del current_user
    return list_product_mappings(session, product_id)


@router.post(
    "/{product_id}/mappings",
    response_model=ProductMappingResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_product_mapping(
    product_id: int,
    payload: ProductMappingCreate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return create_product_mapping(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.patch(
    "/{product_id}/mappings/{mapping_id}",
    response_model=ProductMappingResponse,
)
def patch_product_mapping(
    product_id: int,
    mapping_id: int,
    payload: ProductMappingUpdate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return update_product_mapping(
        session,
        product_id=product_id,
        mapping_id=mapping_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.delete(
    "/{product_id}/mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_mapping(
    product_id: int,
    mapping_id: int,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> Response:
    delete_product_mapping(
        session,
        product_id=product_id,
        mapping_id=mapping_id,
        actor=writer,
        request_id=request.state.request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
