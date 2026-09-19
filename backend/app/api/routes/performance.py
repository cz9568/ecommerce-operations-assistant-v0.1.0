from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.performance import (
    PerformanceRecordCreate,
    PerformanceRecordResponse,
    PerformanceRecordUpdate,
    PerformanceSummary,
    ReviewReportGenerateRequest,
    ReviewReportResponse,
    ReviewReportRevisionResponse,
    ReviewReportUpdate,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.performance import (
    _response as performance_response,
)
from backend.app.services.performance import (
    create_performance_record,
    get_performance_record_or_error,
    list_performance_records,
    performance_summary,
    update_performance_record,
    void_performance_record,
)
from backend.app.services.review_reports import (
    _response as review_response,
)
from backend.app.services.review_reports import (
    generate_review_report,
    get_review_report_or_error,
    list_review_reports,
    list_review_revisions,
    update_review_report,
)

router = APIRouter(tags=["经营数据与复盘"])
DatabaseSession = Annotated[Session, Depends(get_db)]
PerformanceWriter = Annotated[User, Depends(require_permissions(Permission.PERFORMANCE_WRITE))]
AiGenerator = Annotated[User, Depends(require_permissions(Permission.AI_GENERATE))]


@router.post(
    "/products/{product_id}/performance-records",
    response_model=PerformanceRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_performance_record(
    product_id: int,
    payload: PerformanceRecordCreate,
    request: Request,
    writer: PerformanceWriter,
    session: DatabaseSession,
) -> dict:
    return create_performance_record(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/performance-records",
    response_model=Page[PerformanceRecordResponse],
)
def get_performance_records(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    record_status: Annotated[Literal["active", "voided"] | None, Query(alias="status")] = None,
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PerformanceRecordResponse]:
    del current_user
    items, total = list_performance_records(
        session,
        product_id=product_id,
        status=record_status,
        period_start=period_start,
        period_end=period_end,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/products/{product_id}/performance-records/summary",
    response_model=PerformanceSummary,
)
def get_performance_summary(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
) -> dict:
    del current_user
    return performance_summary(
        session,
        product_id=product_id,
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/products/{product_id}/performance-records/{record_id}",
    response_model=PerformanceRecordResponse,
)
def get_performance_record(
    product_id: int,
    record_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return performance_response(
        get_performance_record_or_error(session, product_id=product_id, record_id=record_id)
    )


@router.patch(
    "/products/{product_id}/performance-records/{record_id}",
    response_model=PerformanceRecordResponse,
)
def patch_performance_record(
    product_id: int,
    record_id: int,
    payload: PerformanceRecordUpdate,
    request: Request,
    writer: PerformanceWriter,
    session: DatabaseSession,
) -> dict:
    return update_performance_record(
        session,
        product_id=product_id,
        record_id=record_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.delete(
    "/products/{product_id}/performance-records/{record_id}",
    response_model=PerformanceRecordResponse,
)
def delete_performance_record(
    product_id: int,
    record_id: int,
    request: Request,
    writer: PerformanceWriter,
    session: DatabaseSession,
    expected_version: Annotated[int, Query(ge=1)],
) -> dict:
    return void_performance_record(
        session,
        product_id=product_id,
        record_id=record_id,
        expected_version=expected_version,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.post(
    "/products/{product_id}/review-reports/generate",
    response_model=ReviewReportResponse,
)
def post_review_report_generate(
    product_id: int,
    payload: ReviewReportGenerateRequest,
    request: Request,
    generator: AiGenerator,
    session: DatabaseSession,
) -> dict:
    return generate_review_report(
        session,
        product_id=product_id,
        payload=payload,
        actor=generator,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/review-reports",
    response_model=Page[ReviewReportResponse],
)
def get_review_reports(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ReviewReportResponse]:
    del current_user
    items, total = list_review_reports(
        session, product_id=product_id, page=page, page_size=page_size
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/products/{product_id}/review-reports/{report_id}",
    response_model=ReviewReportResponse,
)
def get_review_report(
    product_id: int,
    report_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return review_response(
        session,
        get_review_report_or_error(session, product_id=product_id, report_id=report_id),
    )


@router.patch(
    "/products/{product_id}/review-reports/{report_id}",
    response_model=ReviewReportResponse,
)
def patch_review_report(
    product_id: int,
    report_id: int,
    payload: ReviewReportUpdate,
    request: Request,
    writer: PerformanceWriter,
    session: DatabaseSession,
) -> dict:
    return update_review_report(
        session,
        product_id=product_id,
        report_id=report_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/review-reports/{report_id}/revisions",
    response_model=list[ReviewReportRevisionResponse],
)
def get_review_report_revisions(
    product_id: int,
    report_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[dict]:
    del current_user
    return list_review_revisions(session, product_id=product_id, report_id=report_id)
