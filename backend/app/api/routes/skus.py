from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.skus import (
    SkuCreate,
    SkuResponse,
    SkuStatus,
    SkuStatusUpdate,
    SkuUpdate,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.skus import (
    change_sku_status,
    create_sku,
    get_sku_detail,
    list_skus,
    update_sku,
)

router = APIRouter(prefix="/products/{product_id}/skus", tags=["SKU 管理"])
InventoryWriter = Annotated[User, Depends(require_permissions(Permission.INVENTORY_WRITE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=Page[SkuResponse])
def get_skus(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sku_status: Annotated[SkuStatus | None, Query(alias="status")] = None,
    query: Annotated[str | None, Query(alias="q", max_length=255)] = None,
) -> Page[SkuResponse]:
    del current_user
    skus, total = list_skus(
        session,
        product_id=product_id,
        page=page,
        page_size=page_size,
        status=sku_status,
        query=query,
    )
    return Page(items=skus, page=page, page_size=page_size, total=total)


@router.post("", response_model=SkuResponse, status_code=status.HTTP_201_CREATED)
def post_sku(
    product_id: int,
    payload: SkuCreate,
    request: Request,
    writer: InventoryWriter,
    session: DatabaseSession,
) -> dict:
    return create_sku(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get("/{sku_id}", response_model=SkuResponse)
def get_sku(
    product_id: int,
    sku_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_sku_detail(session, product_id=product_id, sku_id=sku_id)


@router.patch("/{sku_id}", response_model=SkuResponse)
def patch_sku(
    product_id: int,
    sku_id: int,
    payload: SkuUpdate,
    request: Request,
    writer: InventoryWriter,
    session: DatabaseSession,
) -> dict:
    return update_sku(
        session,
        product_id=product_id,
        sku_id=sku_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.patch("/{sku_id}/status", response_model=SkuResponse)
def patch_sku_status(
    product_id: int,
    sku_id: int,
    payload: SkuStatusUpdate,
    request: Request,
    writer: InventoryWriter,
    session: DatabaseSession,
) -> dict:
    return change_sku_status(
        session,
        product_id=product_id,
        sku_id=sku_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )
