from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import Permission, require_permissions
from backend.app.api.schemas.imports import ImportBatchPage, ImportPreviewResponse, ImportType
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.imports import (
    confirm_batch,
    error_csv,
    list_batches,
    preview_batch,
    template_csv,
    upload_and_preview,
)

router = APIRouter(prefix="/imports", tags=["导入中心"])
DatabaseSession = Annotated[Session, Depends(get_db)]
Importer = Annotated[User, Depends(require_permissions(Permission.PRODUCT_WRITE))]


@router.get("/templates/{import_type}")
def get_import_template(import_type: ImportType, importer: Importer) -> Response:
    del importer
    content = template_csv(import_type)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{import_type}-template.csv"'},
    )


@router.post("/{import_type}/upload", response_model=ImportPreviewResponse)
async def post_import_upload(
    import_type: ImportType,
    request: Request,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
    idempotency_key: Annotated[
        str, Header(alias="X-Idempotency-Key", min_length=8, max_length=128)
    ],
    importer: Importer,
    session: DatabaseSession,
) -> dict:
    return upload_and_preview(
        session,
        import_type=import_type,
        filename=filename,
        content=await request.body(),
        idempotency_key=idempotency_key,
        actor=importer,
        request_id=request.state.request_id,
    )


@router.get("", response_model=ImportBatchPage)
def get_import_batches(
    importer: Importer,
    session: DatabaseSession,
    import_type: Annotated[ImportType | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    del importer
    items, total = list_batches(session, page=page, page_size=page_size, import_type=import_type)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/{batch_id}", response_model=ImportPreviewResponse)
def get_import_batch(batch_id: int, importer: Importer, session: DatabaseSession) -> dict:
    del importer
    return preview_batch(session, batch_id)


@router.post("/{batch_id}/confirm", response_model=ImportPreviewResponse)
def post_import_confirm(
    batch_id: int,
    request: Request,
    importer: Importer,
    session: DatabaseSession,
) -> dict:
    return confirm_batch(
        session,
        batch_id=batch_id,
        actor=importer,
        request_id=request.state.request_id,
    )


@router.get("/{batch_id}/errors.csv")
def get_import_errors(batch_id: int, importer: Importer, session: DatabaseSession) -> Response:
    del importer
    return Response(
        content=error_csv(session, batch_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="import-{batch_id}-errors.csv"'},
    )
