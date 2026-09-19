from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.platform_accounts import (
    AuthorizationCallback,
    AuthorizationStartResponse,
    PlatformAccountCreate,
    PlatformAccountResponse,
    PlatformAccountUpdate,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.platform_accounts import (
    complete_authorization,
    create_platform_account,
    get_platform_account,
    list_platform_accounts,
    revoke_authorization,
    start_authorization,
    update_platform_account,
)

router = APIRouter(tags=["平台账号"])
StoreManager = Annotated[User, Depends(require_permissions(Permission.STORE_MANAGE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/stores/{store_id}/platform-accounts",
    response_model=list[PlatformAccountResponse],
)
def get_store_platform_accounts(
    store_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[dict]:
    del current_user
    return list_platform_accounts(session, store_id)


@router.post(
    "/stores/{store_id}/platform-accounts",
    response_model=PlatformAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_store_platform_account(
    store_id: int,
    payload: PlatformAccountCreate,
    request: Request,
    manager: StoreManager,
    session: DatabaseSession,
) -> dict:
    return create_platform_account(
        session,
        store_id=store_id,
        payload=payload,
        actor=manager,
        request_id=request.state.request_id,
    )


@router.get("/platform-accounts/{account_id}", response_model=PlatformAccountResponse)
def get_account(
    account_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_platform_account(session, account_id)


@router.patch("/platform-accounts/{account_id}", response_model=PlatformAccountResponse)
def patch_account(
    account_id: int,
    payload: PlatformAccountUpdate,
    request: Request,
    manager: StoreManager,
    session: DatabaseSession,
) -> dict:
    return update_platform_account(
        session,
        account_id=account_id,
        payload=payload,
        actor=manager,
        request_id=request.state.request_id,
    )


@router.post(
    "/platform-accounts/{account_id}/authorization/start",
    response_model=AuthorizationStartResponse,
)
def post_authorization_start(
    account_id: int,
    request: Request,
    manager: StoreManager,
    session: DatabaseSession,
) -> dict:
    return start_authorization(
        session,
        account_id=account_id,
        actor=manager,
        request_id=request.state.request_id,
    )


@router.post(
    "/platform-accounts/{account_id}/authorization/callback",
    response_model=PlatformAccountResponse,
)
def post_authorization_callback(
    account_id: int,
    payload: AuthorizationCallback,
    request: Request,
    session: DatabaseSession,
) -> dict:
    return complete_authorization(
        session,
        account_id=account_id,
        payload=payload,
        request_id=request.state.request_id,
    )


@router.post(
    "/platform-accounts/{account_id}/authorization/revoke",
    response_model=PlatformAccountResponse,
)
def post_authorization_revoke(
    account_id: int,
    request: Request,
    manager: StoreManager,
    session: DatabaseSession,
) -> dict:
    return revoke_authorization(
        session,
        account_id=account_id,
        actor=manager,
        request_id=request.state.request_id,
    )
