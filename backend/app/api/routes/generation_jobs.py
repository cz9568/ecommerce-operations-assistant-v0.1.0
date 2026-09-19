from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.generation_jobs import (
    GenerationJobActionRequest,
    GenerationJobCreate,
    GenerationJobEventResponse,
    GenerationJobResponse,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.generation_jobs import (
    cancel_generation_job,
    create_generation_job,
    get_generation_job,
    list_generation_job_events,
    list_generation_jobs,
    retry_generation_job,
)

router = APIRouter(prefix="/products/{product_id}/generation-jobs", tags=["异步生成任务"])
AiGenerator = Annotated[User, Depends(require_permissions(Permission.AI_GENERATE))]
JobOperator = Annotated[User, Depends(require_permissions(Permission.JOB_OPERATE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=GenerationJobResponse)
def post_generation_job(
    product_id: int,
    payload: GenerationJobCreate,
    request: Request,
    response: Response,
    generator: AiGenerator,
    session: DatabaseSession,
) -> dict:
    result, created = create_generation_job(
        session,
        product_id=product_id,
        payload=payload,
        actor=generator,
        request_id=request.state.request_id,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return result


@router.get("", response_model=Page[GenerationJobResponse])
def get_generation_jobs(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    job_kind: Annotated[Literal["image", "video"] | None, Query()] = None,
    job_status: Annotated[
        Literal["pending", "running", "succeeded", "failed", "cancelled", "timeout"] | None,
        Query(),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[GenerationJobResponse]:
    del current_user
    items, total = list_generation_jobs(
        session,
        product_id=product_id,
        job_kind=job_kind,
        job_status=job_status,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/{job_id}", response_model=GenerationJobResponse)
def get_generation_job_detail(
    product_id: int,
    job_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_generation_job(session, product_id=product_id, job_id=job_id)


@router.get("/{job_id}/events", response_model=list[GenerationJobEventResponse])
def get_generation_job_event_timeline(
    product_id: int,
    job_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[dict]:
    del current_user
    return list_generation_job_events(session, product_id=product_id, job_id=job_id)


@router.post("/{job_id}/cancel", response_model=GenerationJobResponse)
def post_generation_job_cancel(
    product_id: int,
    job_id: int,
    payload: GenerationJobActionRequest,
    request: Request,
    operator: JobOperator,
    session: DatabaseSession,
) -> dict:
    return cancel_generation_job(
        session,
        product_id=product_id,
        job_id=job_id,
        payload=payload,
        actor=operator,
        request_id=request.state.request_id,
    )


@router.post("/{job_id}/retry", response_model=GenerationJobResponse)
def post_generation_job_retry(
    product_id: int,
    job_id: int,
    payload: GenerationJobActionRequest,
    request: Request,
    operator: JobOperator,
    session: DatabaseSession,
) -> dict:
    return retry_generation_job(
        session,
        product_id=product_id,
        job_id=job_id,
        payload=payload,
        actor=operator,
        request_id=request.state.request_id,
    )
