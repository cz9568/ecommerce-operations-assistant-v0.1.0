from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.schemas.users import UserCreate, UserUpdate
from backend.app.errors import AppError
from backend.app.models.entities import User
from backend.app.security import hash_password
from backend.app.services.audit import add_audit_log


def list_users(
    session: Session,
    *,
    page: int,
    page_size: int,
    role: str | None,
    status: str | None,
    query: str | None,
) -> tuple[list[User], int]:
    filters = []
    if role:
        filters.append(User.role == role)
    if status:
        filters.append(User.status == status)
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(or_(User.username.like(pattern), User.display_name.like(pattern)))

    total = session.scalar(select(func.count(User.id)).where(*filters)) or 0
    users = list(
        session.scalars(
            select(User)
            .where(*filters)
            .order_by(User.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return users, total


def create_user(
    session: Session,
    *,
    payload: UserCreate,
    actor: User,
    request_id: str | None,
) -> User:
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        status=payload.status,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "USERNAME_EXISTS", "用户名已存在") from exc

    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="user.create",
        target_type="user",
        target_id=user.id,
        request_id=request_id,
        detail={"role": user.role, "status": user.status},
    )
    session.commit()
    session.refresh(user)
    return user


def update_user(
    session: Session,
    *,
    user_id: int,
    payload: UserUpdate,
    actor: User,
    request_id: str | None,
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "用户不存在")

    data = payload.model_dump(exclude_unset=True)
    resulting_role = data.get("role", user.role)
    resulting_status = data.get("status", user.status)
    removes_active_admin = (
        user.role == "admin"
        and user.status == "active"
        and (resulting_role != "admin" or resulting_status != "active")
    )
    if removes_active_admin:
        active_admins = session.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.status == "active")
        )
        if (active_admins or 0) <= 1:
            raise AppError(409, "LAST_ADMIN_REQUIRED", "不能停用或降级最后一个有效管理员")

    old_role = user.role
    old_status = user.status
    password_changed = "password" in data
    if password_changed:
        user.password_hash = hash_password(data.pop("password"))
    for field_name, value in data.items():
        setattr(user, field_name, value)

    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="user.update",
        target_type="user",
        target_id=user.id,
        request_id=request_id,
        detail={
            "old_role": old_role,
            "new_role": user.role,
            "old_status": old_status,
            "new_status": user.status,
            "password_changed": password_changed,
        },
    )
    session.commit()
    session.refresh(user)
    return user
