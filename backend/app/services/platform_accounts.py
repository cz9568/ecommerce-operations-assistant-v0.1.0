import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.schemas.platform_accounts import (
    AuthorizationCallback,
    PlatformAccountCreate,
    PlatformAccountUpdate,
)
from backend.app.errors import AppError
from backend.app.models.entities import PlatformAccount, User
from backend.app.services.audit import add_audit_log
from backend.app.services.stores import get_store_or_error

PUBLIC_AUTH_META_KEYS = frozenset(
    {"seller_id", "scopes", "expires_at", "last_authorized_at", "last_error_code"}
)
PERSISTED_AUTH_META_KEYS = PUBLIC_AUTH_META_KEYS | frozenset(
    {"authorization_state_hash", "authorization_started_at"}
)


def _get_account_or_error(session: Session, account_id: int) -> PlatformAccount:
    account = session.get(PlatformAccount, account_id)
    if account is None:
        raise AppError(404, "PLATFORM_ACCOUNT_NOT_FOUND", "平台账号不存在")
    return account


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _mask_account_name(value: str) -> str:
    if "@" in value:
        local, domain = value.rsplit("@", 1)
        return f"{local[:1] or '*'}***@{domain}"
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) >= 7 and len(digits) == len(value):
        return f"{value[:3]}****{value[-4:]}"
    if len(value) <= 2:
        return "*" * len(value)
    if len(value) <= 4:
        return f"{value[0]}**{value[-1]}"
    return f"{value[:2]}***{value[-2:]}"


def _public_auth_meta(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {key: value[key] for key in PUBLIC_AUTH_META_KEYS if key in value}


def _account_response(account: PlatformAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "store_id": account.store_id,
        "platform": account.platform,
        "account_name_masked": _mask_account_name(account.account_name),
        "auth_status": account.auth_status,
        "auth_meta": _public_auth_meta(account.auth_meta_json),
        "remark": account.remark,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


def list_platform_accounts(session: Session, store_id: int) -> list[dict[str, Any]]:
    get_store_or_error(session, store_id)
    accounts = session.scalars(
        select(PlatformAccount)
        .where(PlatformAccount.store_id == store_id)
        .order_by(PlatformAccount.id.asc())
    ).all()
    return [_account_response(account) for account in accounts]


def get_platform_account(session: Session, account_id: int) -> dict[str, Any]:
    return _account_response(_get_account_or_error(session, account_id))


def create_platform_account(
    session: Session,
    *,
    store_id: int,
    payload: PlatformAccountCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    store = get_store_or_error(session, store_id)
    account = PlatformAccount(
        store_id=store.id,
        platform=store.platform,
        account_name=payload.account_name,
        auth_status="unconfigured",
        auth_meta_json=None,
        remark=payload.remark,
    )
    session.add(account)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "PLATFORM_ACCOUNT_EXISTS", "该店铺平台账号已存在") from exc
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="platform_account.create",
        target_type="platform_account",
        target_id=account.id,
        request_id=request_id,
        detail={"store_id": store.id, "platform": store.platform},
    )
    session.commit()
    session.refresh(account)
    return _account_response(account)


def update_platform_account(
    session: Session,
    *,
    account_id: int,
    payload: PlatformAccountUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    account = _get_account_or_error(session, account_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field_name, value)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "PLATFORM_ACCOUNT_EXISTS", "该店铺平台账号已存在") from exc
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="platform_account.update",
        target_type="platform_account",
        target_id=account.id,
        request_id=request_id,
        detail={"store_id": account.store_id},
    )
    session.commit()
    session.refresh(account)
    return _account_response(account)


def start_authorization(
    session: Session,
    *,
    account_id: int,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    account = _get_account_or_error(session, account_id)
    state = secrets.token_urlsafe(32)
    account.auth_status = "pending"
    account.auth_meta_json = {
        "authorization_state_hash": _state_hash(state),
        "authorization_started_at": datetime.now(UTC).isoformat(),
    }
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="platform_account.authorization_start",
        target_type="platform_account",
        target_id=account.id,
        request_id=request_id,
        detail={"store_id": account.store_id, "platform": account.platform},
    )
    session.commit()
    return {
        "account_id": account.id,
        "auth_status": "pending",
        "state": state,
        "authorization_url": None,
        "callback_path": f"/api/v1/platform-accounts/{account.id}/authorization/callback",
        "message": "授权流程为安全占位；接入平台后在此返回真实授权地址",
    }


def complete_authorization(
    session: Session,
    *,
    account_id: int,
    payload: AuthorizationCallback,
    request_id: str | None,
) -> dict[str, Any]:
    account = _get_account_or_error(session, account_id)
    metadata = account.auth_meta_json or {}
    expected_hash = metadata.get("authorization_state_hash")
    if (
        account.auth_status != "pending"
        or not isinstance(expected_hash, str)
        or not hmac.compare_digest(expected_hash, _state_hash(payload.state))
    ):
        raise AppError(400, "INVALID_AUTHORIZATION_STATE", "授权状态无效或已使用")

    now = datetime.now(UTC).isoformat()
    safe_metadata: dict[str, Any] = {}
    if payload.result == "authorized":
        safe_metadata = {
            "seller_id": payload.seller_id,
            "scopes": payload.scopes,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
            "last_authorized_at": now,
        }
    elif payload.error_code:
        safe_metadata = {"last_error_code": payload.error_code}
    account.auth_status = payload.result
    account.auth_meta_json = {
        key: value
        for key, value in safe_metadata.items()
        if key in PERSISTED_AUTH_META_KEYS and value is not None
    }
    add_audit_log(
        session,
        actor_user_id=None,
        action="platform_account.authorization_callback",
        target_type="platform_account",
        target_id=account.id,
        request_id=request_id,
        detail={"result": payload.result, "platform": account.platform},
    )
    session.commit()
    session.refresh(account)
    return _account_response(account)


def revoke_authorization(
    session: Session,
    *,
    account_id: int,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    account = _get_account_or_error(session, account_id)
    account.auth_status = "revoked"
    account.auth_meta_json = None
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="platform_account.authorization_revoke",
        target_type="platform_account",
        target_id=account.id,
        request_id=request_id,
        detail={"store_id": account.store_id, "platform": account.platform},
    )
    session.commit()
    session.refresh(account)
    return _account_response(account)
