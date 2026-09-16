from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.entities import AuditLog


def add_audit_log(
    session: Session,
    *,
    actor_user_id: int | None,
    action: str,
    target_type: str,
    target_id: str | int | None = None,
    request_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        request_id=request_id,
        detail_json=detail,
    )
    session.add(audit_log)
    return audit_log
