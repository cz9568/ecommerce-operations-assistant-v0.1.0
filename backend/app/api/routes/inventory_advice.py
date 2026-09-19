from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.inventory_advice import (
    InventoryAdviceGenerateRequest,
    InventoryAdviceRunResponse,
    InventoryAdviceRunSummary,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.inventory_advice import (
    generate_inventory_advice,
    get_inventory_advice_run,
    get_latest_inventory_advice,
    list_inventory_advice_runs,
)

router = APIRouter(prefix="/stores/{store_id}/inventory-advice", tags=["库存建议"])
InventoryWriter = Annotated[User, Depends(require_permissions(Permission.INVENTORY_WRITE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("/generate", response_model=InventoryAdviceRunResponse)
def post_inventory_advice(
    store_id: int,
    payload: InventoryAdviceGenerateRequest,
    request: Request,
    writer: InventoryWriter,
    session: DatabaseSession,
) -> dict:
    return generate_inventory_advice(
        session,
        store_id=store_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get("", response_model=InventoryAdviceRunResponse)
def get_latest_advice(
    store_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_latest_inventory_advice(session, store_id)


@router.get("/runs", response_model=Page[InventoryAdviceRunSummary])
def get_advice_runs(
    store_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[InventoryAdviceRunSummary]:
    del current_user
    items, total = list_inventory_advice_runs(
        session,
        store_id=store_id,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/runs/{run_id}", response_model=InventoryAdviceRunResponse)
def get_advice_run(
    store_id: int,
    run_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_inventory_advice_run(session, store_id=store_id, run_id=run_id)
