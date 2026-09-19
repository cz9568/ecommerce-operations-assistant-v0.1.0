from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.competitors import (
    CompetitorCreate,
    CompetitorResponse,
    CompetitorStatus,
    CompetitorUpdate,
    MonitorResponse,
    MonitorRunSummary,
    MonitorSnapshotResponse,
    MonitorUpsert,
    ParseTaskApply,
    ParseTaskCreate,
    ParseTaskResponse,
    ParseTaskStatus,
    SnapshotApply,
)
from backend.app.api.schemas.stores import StorePlatform
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.competitors import (
    _competitor_response,
    _task_response,
    apply_parse_task,
    apply_snapshot,
    archive_competitor,
    create_competitor,
    create_parse_task,
    get_competitor_or_error,
    get_monitor,
    get_parse_task_or_error,
    list_competitors,
    list_parse_tasks,
    list_snapshots,
    run_due_monitors,
    run_monitor,
    run_parse_task,
    update_competitor,
    upsert_monitor,
)

router = APIRouter(tags=["竞品管理"])
CompetitorWriter = Annotated[User, Depends(require_permissions(Permission.COMPETITOR_WRITE))]
JobOperator = Annotated[User, Depends(require_permissions(Permission.JOB_OPERATE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/products/{product_id}/competitors", response_model=Page[CompetitorResponse])
def get_competitors(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    competitor_status: Annotated[CompetitorStatus | None, Query(alias="status")] = None,
    platform: StorePlatform | None = None,
    query: Annotated[str | None, Query(alias="q", max_length=255)] = None,
) -> Page[CompetitorResponse]:
    del current_user
    items, total = list_competitors(
        session,
        product_id=product_id,
        page=page,
        page_size=page_size,
        status=competitor_status,
        platform=platform,
        query=query,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post(
    "/products/{product_id}/competitors",
    response_model=CompetitorResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_competitor(
    product_id: int,
    payload: CompetitorCreate,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return create_competitor(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/competitors/{competitor_id}",
    response_model=CompetitorResponse,
)
def get_competitor(
    product_id: int,
    competitor_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return _competitor_response(
        get_competitor_or_error(session, product_id=product_id, competitor_id=competitor_id)
    )


@router.patch(
    "/products/{product_id}/competitors/{competitor_id}",
    response_model=CompetitorResponse,
)
def patch_competitor(
    product_id: int,
    competitor_id: int,
    payload: CompetitorUpdate,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return update_competitor(
        session,
        product_id=product_id,
        competitor_id=competitor_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.delete(
    "/products/{product_id}/competitors/{competitor_id}",
    response_model=CompetitorResponse,
)
def delete_competitor(
    product_id: int,
    competitor_id: int,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return archive_competitor(
        session,
        product_id=product_id,
        competitor_id=competitor_id,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.post(
    "/products/{product_id}/competitors/import-url-tasks",
    response_model=ParseTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_parse_task(
    product_id: int,
    payload: ParseTaskCreate,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return create_parse_task(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/link-parse-tasks",
    response_model=Page[ParseTaskResponse],
)
def get_parse_tasks(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    task_status: Annotated[ParseTaskStatus | None, Query(alias="status")] = None,
) -> Page[ParseTaskResponse]:
    del current_user
    items, total = list_parse_tasks(
        session,
        product_id=product_id,
        page=page,
        page_size=page_size,
        status=task_status,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/products/{product_id}/link-parse-tasks/{task_id}",
    response_model=ParseTaskResponse,
)
def get_parse_task(
    product_id: int,
    task_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return _task_response(get_parse_task_or_error(session, product_id=product_id, task_id=task_id))


@router.post(
    "/products/{product_id}/link-parse-tasks/{task_id}/run",
    response_model=ParseTaskResponse,
)
def post_parse_task_run(
    product_id: int,
    task_id: int,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return run_parse_task(
        session,
        product_id=product_id,
        task_id=task_id,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.post(
    "/products/{product_id}/link-parse-tasks/{task_id}/apply",
    response_model=CompetitorResponse,
)
def post_parse_task_apply(
    product_id: int,
    task_id: int,
    payload: ParseTaskApply,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return apply_parse_task(
        session,
        product_id=product_id,
        task_id=task_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/competitors/{competitor_id}/monitor",
    response_model=MonitorResponse,
)
def get_competitor_monitor(
    product_id: int,
    competitor_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_monitor(session, product_id=product_id, competitor_id=competitor_id)


@router.post(
    "/products/{product_id}/competitors/{competitor_id}/monitor",
    response_model=MonitorResponse,
)
def post_competitor_monitor(
    product_id: int,
    competitor_id: int,
    payload: MonitorUpsert,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return upsert_monitor(
        session,
        product_id=product_id,
        competitor_id=competitor_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.patch(
    "/products/{product_id}/competitors/{competitor_id}/monitor",
    response_model=MonitorResponse,
)
def patch_competitor_monitor(
    product_id: int,
    competitor_id: int,
    payload: MonitorUpsert,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return post_competitor_monitor(product_id, competitor_id, payload, request, writer, session)


@router.post(
    "/products/{product_id}/competitors/{competitor_id}/monitor/run",
    response_model=MonitorResponse,
)
def post_competitor_monitor_run(
    product_id: int,
    competitor_id: int,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    del writer
    return run_monitor(session, product_id=product_id, competitor_id=competitor_id, force=True)


@router.get(
    "/products/{product_id}/competitors/{competitor_id}/monitor/snapshots",
    response_model=Page[MonitorSnapshotResponse],
)
def get_competitor_monitor_snapshots(
    product_id: int,
    competitor_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[MonitorSnapshotResponse]:
    del current_user
    items, total = list_snapshots(
        session,
        product_id=product_id,
        competitor_id=competitor_id,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post(
    "/products/{product_id}/competitors/{competitor_id}/monitor/snapshots/{snapshot_id}/apply",
    response_model=CompetitorResponse,
)
def post_snapshot_apply(
    product_id: int,
    competitor_id: int,
    snapshot_id: int,
    payload: SnapshotApply,
    request: Request,
    writer: CompetitorWriter,
    session: DatabaseSession,
) -> dict:
    return apply_snapshot(
        session,
        product_id=product_id,
        competitor_id=competitor_id,
        snapshot_id=snapshot_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.post(
    "/workspace/competitor-monitors/run-due",
    response_model=MonitorRunSummary,
)
def post_run_due_monitors(
    operator: JobOperator,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, int]:
    del operator
    return run_due_monitors(session, limit=limit)
