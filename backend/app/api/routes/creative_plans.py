from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.creative_plans import (
    CreativePlanGenerateRequest,
    CreativePlanResponse,
    CreativePlanRevisionResponse,
    CreativePlanStatusUpdate,
    CreativePlanUpdate,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.creative_plans import (
    generate_creative_plans,
    get_creative_plan,
    list_creative_plans,
    list_plan_revisions,
    update_creative_plan,
    update_creative_plan_status,
)

router = APIRouter(prefix="/products/{product_id}/creative-plans", tags=["创意方案"])
AiGenerator = Annotated[User, Depends(require_permissions(Permission.AI_GENERATE))]
ProductWriter = Annotated[User, Depends(require_permissions(Permission.PRODUCT_WRITE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/generate",
    response_model=list[CreativePlanResponse],
    status_code=status.HTTP_201_CREATED,
)
def post_creative_plan_generation(
    product_id: int,
    payload: CreativePlanGenerateRequest,
    request: Request,
    generator: AiGenerator,
    session: DatabaseSession,
) -> list[dict]:
    return generate_creative_plans(
        session,
        product_id=product_id,
        payload=payload,
        actor=generator,
        request_id=request.state.request_id,
    )


@router.get("", response_model=Page[CreativePlanResponse])
def get_creative_plans(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    plan_type: Annotated[Literal["main_image", "video_script"], Query()],
    plan_status: Annotated[Literal["draft", "selected", "archived"] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CreativePlanResponse]:
    del current_user
    items, total = list_creative_plans(
        session,
        product_id=product_id,
        plan_type=plan_type,
        status=plan_status,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/{plan_id}", response_model=CreativePlanResponse)
def get_creative_plan_detail(
    product_id: int,
    plan_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_creative_plan(session, product_id=product_id, plan_id=plan_id)


@router.get("/{plan_id}/revisions", response_model=list[CreativePlanRevisionResponse])
def get_creative_plan_revisions(
    product_id: int,
    plan_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[dict]:
    del current_user
    return list_plan_revisions(session, product_id=product_id, plan_id=plan_id)


@router.patch("/{plan_id}", response_model=CreativePlanResponse)
def patch_creative_plan(
    product_id: int,
    plan_id: int,
    payload: CreativePlanUpdate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return update_creative_plan(
        session,
        product_id=product_id,
        plan_id=plan_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.post("/{plan_id}/status", response_model=CreativePlanResponse)
def post_creative_plan_status(
    product_id: int,
    plan_id: int,
    payload: CreativePlanStatusUpdate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return update_creative_plan_status(
        session,
        product_id=product_id,
        plan_id=plan_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )
