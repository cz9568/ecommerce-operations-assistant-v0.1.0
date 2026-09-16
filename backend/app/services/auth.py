from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.errors import AppError
from backend.app.models.entities import AuthTokenRevocation, User
from backend.app.security import hash_password, verify_password
from backend.app.services.audit import add_audit_log

DUMMY_PASSWORD_HASH = hash_password("Not-A-Real-Password-123")


def authenticate_user(session: Session, username: str, password: str) -> User:
    user = session.scalar(select(User).where(User.username == username))
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_matches = verify_password(password, password_hash)

    if user is None or not password_matches:
        raise AppError(401, "INVALID_CREDENTIALS", "用户名或密码错误")
    if user.status != "active":
        raise AppError(403, "USER_INACTIVE", "用户已被停用")
    return user


def record_login(session: Session, user: User, request_id: str | None) -> None:
    user.last_login_at = datetime.now(UTC)
    add_audit_log(
        session,
        actor_user_id=user.id,
        action="auth.login",
        target_type="user",
        target_id=user.id,
        request_id=request_id,
    )


def revoke_token(
    session: Session,
    *,
    user: User,
    jti: str,
    expires_at: datetime,
    request_id: str | None,
) -> None:
    existing = session.scalar(select(AuthTokenRevocation).where(AuthTokenRevocation.jti == jti))
    if existing is None:
        session.add(AuthTokenRevocation(jti=jti, user_id=user.id, expires_at=expires_at))
    add_audit_log(
        session,
        actor_user_id=user.id,
        action="auth.logout",
        target_type="user",
        target_id=user.id,
        request_id=request_id,
    )
