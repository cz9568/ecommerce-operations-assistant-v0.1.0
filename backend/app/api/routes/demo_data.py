from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import Permission, require_permissions
from backend.app.api.schemas.imports import DemoDataResponse
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.demo_data import initialize_demo_data

router = APIRouter(prefix="/demo-data", tags=["演示数据"])
DatabaseSession = Annotated[Session, Depends(get_db)]
Administrator = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


@router.post("/initialize", response_model=DemoDataResponse)
def post_demo_data_initialize(
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
    rebuild: Annotated[bool, Query()] = False,
) -> dict:
    return initialize_demo_data(
        session,
        actor=administrator,
        request_id=request.state.request_id,
        rebuild=rebuild,
    )
