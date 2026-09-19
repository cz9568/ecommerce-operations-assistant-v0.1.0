from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import Permission, require_permissions
from backend.app.api.schemas.settings import SettingGroup, SettingsResponse, SettingsUpdate
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.settings import settings_response, update_settings

router = APIRouter(prefix="/settings", tags=["系统设置"])
DatabaseSession = Annotated[Session, Depends(get_db)]
Administrator = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


@router.get("", response_model=SettingsResponse)
def get_system_settings(administrator: Administrator, session: DatabaseSession) -> dict:
    del administrator
    return settings_response(session)


@router.patch("/{group}", response_model=SettingsResponse)
def patch_system_settings(
    group: SettingGroup,
    payload: SettingsUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> dict:
    return update_settings(
        session,
        group=group,
        payload=payload,
        actor=administrator,
        request_id=request.state.request_id,
    )
