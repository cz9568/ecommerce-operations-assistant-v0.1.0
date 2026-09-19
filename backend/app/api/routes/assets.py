from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.assets import AssetResponse, AssetReviewRequest, AssetUpdate
from backend.app.api.schemas.common import Page
from backend.app.database import get_db
from backend.app.integrations.storage import MediaDownloader, get_storage_adapter
from backend.app.models.entities import User
from backend.app.services.assets import (
    check_asset_file,
    get_asset,
    get_asset_content_path,
    list_assets,
    review_asset,
    sync_succeeded_job_assets,
    update_asset,
)

router = APIRouter(prefix="/products/{product_id}/assets", tags=["素材库"])
DatabaseSession = Annotated[Session, Depends(get_db)]
AssetReviewer = Annotated[User, Depends(require_permissions(Permission.ASSET_REVIEW))]


@router.get("", response_model=Page[AssetResponse])
def get_assets(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    asset_type: Annotated[Literal["image", "video"] | None, Query()] = None,
    review_status: Annotated[Literal["pending", "approved", "rejected"] | None, Query()] = None,
    file_status: Annotated[Literal["available", "missing", "invalid"] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AssetResponse]:
    del current_user
    items, total = list_assets(
        session,
        product_id=product_id,
        asset_type=asset_type,
        review_status=review_status,
        file_status=file_status,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("/sync/{job_id}", response_model=list[AssetResponse])
def post_asset_sync(
    product_id: int,
    job_id: int,
    request: Request,
    reviewer: AssetReviewer,
    session: DatabaseSession,
) -> list[dict]:
    return sync_succeeded_job_assets(
        session,
        product_id=product_id,
        job_id=job_id,
        storage=get_storage_adapter(),
        downloader=MediaDownloader(),
        actor=reviewer,
        request_id=request.state.request_id,
    )


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset_detail(
    product_id: int,
    asset_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_asset(session, product_id=product_id, asset_id=asset_id)


@router.get("/{asset_id}/content", response_class=FileResponse)
def get_asset_content(
    product_id: int,
    asset_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> FileResponse:
    del current_user
    path, media_type, filename = get_asset_content_path(
        session,
        product_id=product_id,
        asset_id=asset_id,
        storage=get_storage_adapter(),
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"},
    )


@router.patch("/{asset_id}", response_model=AssetResponse)
def patch_asset(
    product_id: int,
    asset_id: int,
    payload: AssetUpdate,
    request: Request,
    reviewer: AssetReviewer,
    session: DatabaseSession,
) -> dict:
    return update_asset(
        session,
        product_id=product_id,
        asset_id=asset_id,
        payload=payload,
        actor=reviewer,
        request_id=request.state.request_id,
    )


@router.post("/{asset_id}/review", response_model=AssetResponse)
def post_asset_review(
    product_id: int,
    asset_id: int,
    payload: AssetReviewRequest,
    request: Request,
    reviewer: AssetReviewer,
    session: DatabaseSession,
) -> dict:
    return review_asset(
        session,
        product_id=product_id,
        asset_id=asset_id,
        payload=payload,
        actor=reviewer,
        request_id=request.state.request_id,
        storage=get_storage_adapter(),
    )


@router.post("/{asset_id}/check", response_model=AssetResponse)
def post_asset_file_check(
    product_id: int,
    asset_id: int,
    request: Request,
    reviewer: AssetReviewer,
    session: DatabaseSession,
) -> dict:
    return check_asset_file(
        session,
        product_id=product_id,
        asset_id=asset_id,
        storage=get_storage_adapter(),
        actor=reviewer,
        request_id=request.state.request_id,
    )
