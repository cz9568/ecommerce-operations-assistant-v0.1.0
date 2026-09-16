from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import get_settings
from backend.app.database import engine

router = APIRouter(prefix="/health", tags=["系统健康"])


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    service: str
    database: Literal["not_checked", "ok", "unavailable"]


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, database="not_checked")


@router.get("/ready", response_model=HealthResponse)
def readiness() -> HealthResponse:
    settings = get_settings()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库暂不可用，请检查服务与本地 .env 配置。",
        ) from exc
    return HealthResponse(status="ok", service=settings.app_name, database="ok")
