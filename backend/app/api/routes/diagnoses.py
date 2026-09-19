from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.diagnoses import (
    DiagnosisGenerateRequest,
    DiagnosisResponse,
    DiagnosisUpdate,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.diagnoses import (
    generate_diagnosis,
    get_diagnosis,
    list_diagnoses,
    update_diagnosis,
)

router = APIRouter(prefix="/products/{product_id}/diagnoses", tags=["商品诊断"])
AiGenerator = Annotated[User, Depends(require_permissions(Permission.AI_GENERATE))]
ProductWriter = Annotated[User, Depends(require_permissions(Permission.PRODUCT_WRITE))]
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("/generate", response_model=DiagnosisResponse)
def post_diagnosis_generate(
    product_id: int,
    payload: DiagnosisGenerateRequest,
    request: Request,
    generator: AiGenerator,
    session: DatabaseSession,
) -> dict:
    return generate_diagnosis(
        session,
        product_id=product_id,
        payload=payload,
        actor=generator,
        request_id=request.state.request_id,
    )


@router.get("", response_model=Page[DiagnosisResponse])
def get_diagnoses(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[DiagnosisResponse]:
    del current_user
    items, total = list_diagnoses(session, product_id=product_id, page=page, page_size=page_size)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/{diagnosis_id}", response_model=DiagnosisResponse)
def get_diagnosis_detail(
    product_id: int,
    diagnosis_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return get_diagnosis(session, product_id=product_id, diagnosis_id=diagnosis_id)


@router.patch("/{diagnosis_id}", response_model=DiagnosisResponse)
def patch_diagnosis(
    product_id: int,
    diagnosis_id: int,
    payload: DiagnosisUpdate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return update_diagnosis(
        session,
        product_id=product_id,
        diagnosis_id=diagnosis_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )
