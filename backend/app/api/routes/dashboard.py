from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser
from backend.app.api.schemas.dashboard import DashboardResponse
from backend.app.database import get_db
from backend.app.services.dashboard import dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["工作台"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    current_user: CurrentUser,
    session: DatabaseSession,
    platform: Annotated[str | None, Query(max_length=50)] = None,
) -> dict:
    del current_user
    return dashboard_summary(session, platform=platform)
