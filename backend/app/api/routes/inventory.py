from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.inventory import (
    InventoryAdjustmentCreate,
    InventoryAdjustmentResponse,
    InventoryConfigUpdate,
    InventoryMovementResponse,
    InventoryMovementType,
    InventoryResponse,
)
from backend.app.api.schemas.skus import SkuStatus
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.inventory import (
    adjust_inventory,
    get_inventory_detail,
    list_inventory,
    list_inventory_movements,
    update_inventory_config,
)

router = APIRouter(tags=["库存管理"])
InventoryWriter = Annotated[User, Depends(require_permissions(Permission.INVENTORY_WRITE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


def _inventory_page(
    session: Session,
    *,
    page: int,
    page_size: int,
    store_id: int | None,
    product_id: int | None,
    sku_status: str | None,
    query: str | None,
    only_low_stock: bool,
) -> Page[InventoryResponse]:
    items, total = list_inventory(
        session,
        page=page,
        page_size=page_size,
        store_id=store_id,
        product_id=product_id,
        sku_status=sku_status,
        query=query,
        only_low_stock=only_low_stock,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/inventory", response_model=Page[InventoryResponse])
def get_inventory_list(
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    store_id: Annotated[int | None, Query(ge=1)] = None,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    sku_status: Annotated[SkuStatus | None, Query(alias="status")] = None,
    query: Annotated[str | None, Query(alias="q", max_length=255)] = None,
) -> Page[InventoryResponse]:
    del current_user
    return _inventory_page(
        session,
        page=page,
        page_size=page_size,
        store_id=store_id,
        product_id=product_id,
        sku_status=sku_status,
        query=query,
        only_low_stock=False,
    )


@router.get("/inventory/low-stock", response_model=Page[InventoryResponse])
def get_low_stock_inventory(
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    store_id: Annotated[int | None, Query(ge=1)] = None,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    sku_status: Annotated[SkuStatus | None, Query(alias="status")] = "active",
    query: Annotated[str | None, Query(alias="q", max_length=255)] = None,
) -> Page[InventoryResponse]:
    del current_user
    return _inventory_page(
        session,
        page=page,
        page_size=page_size,
        store_id=store_id,
        product_id=product_id,
        sku_status=sku_status,
        query=query,
        only_low_stock=True,
    )


@router.get(
    "/products/{product_id}/skus/{sku_id}/inventory",
    response_model=InventoryResponse,
)
def get_sku_inventory(
    product_id: int,
    sku_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_inventory_detail(session, product_id=product_id, sku_id=sku_id)


@router.patch(
    "/products/{product_id}/skus/{sku_id}/inventory",
    response_model=InventoryResponse,
)
def patch_sku_inventory(
    product_id: int,
    sku_id: int,
    payload: InventoryConfigUpdate,
    request: Request,
    writer: InventoryWriter,
    session: DatabaseSession,
) -> dict:
    return update_inventory_config(
        session,
        product_id=product_id,
        sku_id=sku_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.post(
    "/products/{product_id}/skus/{sku_id}/inventory/adjustments",
    response_model=InventoryAdjustmentResponse,
)
def post_inventory_adjustment(
    product_id: int,
    sku_id: int,
    payload: InventoryAdjustmentCreate,
    request: Request,
    writer: InventoryWriter,
    session: DatabaseSession,
) -> dict:
    return adjust_inventory(
        session,
        product_id=product_id,
        sku_id=sku_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/skus/{sku_id}/inventory/movements",
    response_model=Page[InventoryMovementResponse],
)
def get_inventory_movements(
    product_id: int,
    sku_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    movement_type: InventoryMovementType | None = None,
) -> Page[InventoryMovementResponse]:
    del current_user
    items, total = list_inventory_movements(
        session,
        product_id=product_id,
        sku_id=sku_id,
        page=page,
        page_size=page_size,
        movement_type=movement_type,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)
