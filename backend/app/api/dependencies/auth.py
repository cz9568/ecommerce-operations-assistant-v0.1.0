from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.errors import AppError
from backend.app.models.entities import AuthTokenRevocation, User
from backend.app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


class Permission(StrEnum):
    USER_MANAGE = "user.manage"
    STORE_MANAGE = "store.manage"
    PRODUCT_WRITE = "product.write"
    INVENTORY_WRITE = "inventory.write"
    COMPETITOR_WRITE = "competitor.write"
    AI_GENERATE = "ai.generate"
    JOB_OPERATE = "job.operate"
    ASSET_REVIEW = "asset.review"
    AD_CONFIRM = "ad.confirm"
    EXPERIMENT_WRITE = "experiment.write"
    PERFORMANCE_WRITE = "performance.write"
    SETTINGS_MANAGE = "settings.manage"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "admin": frozenset(Permission),
    "operator": frozenset(
        {
            Permission.STORE_MANAGE,
            Permission.PRODUCT_WRITE,
            Permission.INVENTORY_WRITE,
            Permission.COMPETITOR_WRITE,
            Permission.AI_GENERATE,
            Permission.JOB_OPERATE,
            Permission.ASSET_REVIEW,
            Permission.AD_CONFIRM,
            Permission.EXPERIMENT_WRITE,
            Permission.PERFORMANCE_WRITE,
        }
    ),
    "viewer": frozenset(),
}


@dataclass(frozen=True)
class AuthContext:
    user: User
    token: str
    jti: str
    expires_at: datetime


def _unauthorized(message: str = "登录状态无效或已过期") -> AppError:
    return AppError(
        401,
        "AUTHENTICATION_REQUIRED",
        message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_auth_context(credentials: BearerCredentials, session: DatabaseSession) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        jti = str(payload["jti"])
        expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise _unauthorized() from exc

    revoked = session.scalar(select(AuthTokenRevocation.id).where(AuthTokenRevocation.jti == jti))
    if revoked is not None:
        raise _unauthorized("登录状态已退出")

    user = session.get(User, user_id)
    if user is None or user.status != "active":
        raise _unauthorized()

    return AuthContext(user=user, token=token, jti=jti, expires_at=expires_at)


def get_current_user(context: Annotated[AuthContext, Depends(get_auth_context)]) -> User:
    return context.user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]


def require_permissions(*required: Permission):
    def permission_dependency(context: CurrentAuth) -> User:
        granted = ROLE_PERMISSIONS.get(context.user.role, frozenset())
        missing = [permission.value for permission in required if permission not in granted]
        if missing:
            raise AppError(
                403,
                "PERMISSION_DENIED",
                "当前角色无权执行此操作",
                details={"required_permissions": missing},
            )
        return context.user

    return permission_dependency
