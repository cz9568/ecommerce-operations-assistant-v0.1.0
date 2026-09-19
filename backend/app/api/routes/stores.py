from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.stores import (
    StoreCreate,
    StorePlatform,
    StoreResponse,
    StoreStatus,
    StoreSummaryResponse,
    StoreUpdate,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.stores import (
    create_store,
    get_store_detail,
    get_store_summary,
    list_stores,
    update_store,
)

router = APIRouter(prefix="/stores", tags=["店铺管理"])
StoreManager = Annotated[User, Depends(require_permissions(Permission.STORE_MANAGE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=Page[StoreResponse])
def get_stores(
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    platform: StorePlatform | None = None,
    store_status: Annotated[StoreStatus | None, Query(alias="status")] = None,
    owner_user_id: Annotated[int | None, Query(ge=1)] = None,
    query: Annotated[str | None, Query(alias="q", max_length=150)] = None,
) -> Page[StoreResponse]:
    del current_user
    stores, total = list_stores(
        session,
        page=page,
        page_size=page_size,
        platform=platform,
        status=store_status,
        owner_user_id=owner_user_id,
        query=query,
    )
    return Page(items=stores, page=page, page_size=page_size, total=total)


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
def post_store(
    payload: StoreCreate,
    request: Request,
    manager: StoreManager,
    session: DatabaseSession,
) -> dict:
    return create_store(
        session,
        payload=payload,
        actor=manager,
        request_id=request.state.request_id,
    )


@router.get("/{store_id}/summary", response_model=StoreSummaryResponse)
def get_store_aggregate(
    store_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_store_summary(session, store_id)


@router.get("/{store_id}", response_model=StoreResponse)
def get_store(
    store_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_store_detail(session, store_id)


@router.patch("/{store_id}", response_model=StoreResponse)
def patch_store(
    store_id: int,
    payload: StoreUpdate,
    request: Request,
    manager: StoreManager,
    session: DatabaseSession,
) -> dict:
    return update_store(
        session,
        store_id=store_id,
        payload=payload,
        actor=manager,
        request_id=request.state.request_id,
    )
