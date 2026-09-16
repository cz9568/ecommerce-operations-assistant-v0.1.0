from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentAuth, CurrentUser
from backend.app.api.schemas.auth import LoginRequest, TokenResponse
from backend.app.api.schemas.common import MessageResponse
from backend.app.api.schemas.users import UserResponse
from backend.app.config import get_settings
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.security import create_access_token
from backend.app.services.auth import authenticate_user, record_login, revoke_token

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = authenticate_user(session, payload.username, payload.password)
    record_login(session, user, request.state.request_id)
    token = create_access_token(str(user.id), extra_claims={"role": user.role})
    session.commit()
    settings = get_settings()
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> User:
    return user


@router.post("/logout", response_model=MessageResponse)
def logout(
    context: CurrentAuth,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    revoke_token(
        session,
        user=context.user,
        jti=context.jti,
        expires_at=context.expires_at,
        request_id=request.state.request_id,
    )
    session.commit()
    return MessageResponse(message="已退出登录")
