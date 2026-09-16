from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.users import UserCreate, UserResponse, UserUpdate
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.users import create_user, list_users, update_user

router = APIRouter(prefix="/users", tags=["用户管理"])
AdminUser = Annotated[User, Depends(require_permissions(Permission.USER_MANAGE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=Page[UserResponse])
def get_users(
    admin: AdminUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    role: Literal["admin", "operator", "viewer"] | None = None,
    user_status: Annotated[Literal["active", "inactive"] | None, Query(alias="status")] = None,
    query: Annotated[str | None, Query(alias="q", max_length=100)] = None,
) -> Page[UserResponse]:
    del admin
    users, total = list_users(
        session,
        page=page,
        page_size=page_size,
        role=role,
        status=user_status,
        query=query,
    )
    return Page(items=users, page=page, page_size=page_size, total=total)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def post_user(
    payload: UserCreate,
    request: Request,
    admin: AdminUser,
    session: DatabaseSession,
) -> User:
    return create_user(
        session,
        payload=payload,
        actor=admin,
        request_id=request.state.request_id,
    )


@router.patch("/{user_id}", response_model=UserResponse)
def patch_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    admin: AdminUser,
    session: DatabaseSession,
) -> User:
    return update_user(
        session,
        user_id=user_id,
        payload=payload,
        actor=admin,
        request_id=request.state.request_id,
    )
