from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import CurrentUser, Permission, require_permissions
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.marketing import (
    AdExperimentGenerateRequest,
    AdExperimentResponse,
    AdExperimentUpdate,
    AdRecommendationConfirmation,
    AdRecommendationGenerateRequest,
    AdRecommendationResponse,
    AdRecommendationUpdate,
    PromotionLinkCreate,
    PromotionLinkResponse,
    PromotionLinkStatistics,
    PromotionLinkSuggestionRequest,
    PromotionLinkSuggestionResponse,
    PromotionLinkUpdate,
)
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.marketing import (
    _experiment_response,
    _link_response,
    _recommendation_response,
    confirm_ad_recommendation,
    create_promotion_link,
    generate_ad_experiment,
    generate_ad_recommendation,
    get_experiment_or_error,
    get_promotion_link_or_error,
    get_recommendation_or_error,
    list_ad_experiments,
    list_ad_recommendations,
    list_promotion_links,
    promotion_link_statistics,
    record_promotion_click,
    suggest_promotion_links,
    update_ad_experiment,
    update_ad_recommendation,
    update_promotion_link,
)

router = APIRouter(tags=["推广链接与投放实验"])
DatabaseSession = Annotated[Session, Depends(get_db)]
ProductWriter = Annotated[User, Depends(require_permissions(Permission.PRODUCT_WRITE))]
AiGenerator = Annotated[User, Depends(require_permissions(Permission.AI_GENERATE))]
AdConfirmer = Annotated[User, Depends(require_permissions(Permission.AD_CONFIRM))]
ExperimentWriter = Annotated[User, Depends(require_permissions(Permission.EXPERIMENT_WRITE))]


@router.post(
    "/products/{product_id}/promotion-links/generate",
    response_model=PromotionLinkSuggestionResponse,
)
def post_promotion_link_suggestions(
    product_id: int,
    payload: PromotionLinkSuggestionRequest,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    del writer
    return {"suggestions": suggest_promotion_links(session, product_id=product_id, payload=payload)}


@router.post(
    "/products/{product_id}/promotion-links",
    response_model=PromotionLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_promotion_link(
    product_id: int,
    payload: PromotionLinkCreate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return create_promotion_link(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/promotion-links",
    response_model=Page[PromotionLinkResponse],
)
def get_promotion_links(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    link_status: Annotated[Literal["active", "inactive"] | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PromotionLinkResponse]:
    del current_user
    items, total = list_promotion_links(
        session,
        product_id=product_id,
        status=link_status,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/products/{product_id}/promotion-links/{link_id}",
    response_model=PromotionLinkResponse,
)
def get_promotion_link(
    product_id: int,
    link_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return _link_response(
        get_promotion_link_or_error(session, product_id=product_id, link_id=link_id)
    )


@router.patch(
    "/products/{product_id}/promotion-links/{link_id}",
    response_model=PromotionLinkResponse,
)
def patch_promotion_link(
    product_id: int,
    link_id: int,
    payload: PromotionLinkUpdate,
    request: Request,
    writer: ProductWriter,
    session: DatabaseSession,
) -> dict:
    return update_promotion_link(
        session,
        product_id=product_id,
        link_id=link_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/promotion-links/{link_id}/statistics",
    response_model=PromotionLinkStatistics,
)
def get_promotion_link_statistics(
    product_id: int,
    link_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
) -> dict:
    del current_user
    end = period_end or datetime.now(UTC).date()
    start = period_start or end - timedelta(days=29)
    return promotion_link_statistics(
        session,
        product_id=product_id,
        link_id=link_id,
        period_start=start,
        period_end=end,
    )


@router.get("/r/{tracking_code}", response_class=RedirectResponse, status_code=307)
def redirect_promotion_link(
    tracking_code: str,
    request: Request,
    session: DatabaseSession,
) -> RedirectResponse:
    target = record_promotion_click(
        session,
        tracking_code=tracking_code,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return RedirectResponse(target, status_code=307)


@router.post(
    "/products/{product_id}/ad-recommendations/generate",
    response_model=AdRecommendationResponse,
)
def post_ad_recommendation_generate(
    product_id: int,
    payload: AdRecommendationGenerateRequest,
    request: Request,
    generator: AiGenerator,
    session: DatabaseSession,
) -> dict:
    return generate_ad_recommendation(
        session,
        product_id=product_id,
        payload=payload,
        actor=generator,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/ad-recommendations",
    response_model=Page[AdRecommendationResponse],
)
def get_ad_recommendations(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdRecommendationResponse]:
    del current_user
    items, total = list_ad_recommendations(
        session, product_id=product_id, page=page, page_size=page_size
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/products/{product_id}/ad-recommendations/{recommendation_id}",
    response_model=AdRecommendationResponse,
)
def get_ad_recommendation(
    product_id: int,
    recommendation_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return _recommendation_response(
        get_recommendation_or_error(
            session, product_id=product_id, recommendation_id=recommendation_id
        )
    )


@router.patch(
    "/products/{product_id}/ad-recommendations/{recommendation_id}",
    response_model=AdRecommendationResponse,
)
def patch_ad_recommendation(
    product_id: int,
    recommendation_id: int,
    payload: AdRecommendationUpdate,
    request: Request,
    confirmer: AdConfirmer,
    session: DatabaseSession,
) -> dict:
    return update_ad_recommendation(
        session,
        product_id=product_id,
        recommendation_id=recommendation_id,
        payload=payload,
        actor=confirmer,
        request_id=request.state.request_id,
    )


@router.patch(
    "/products/{product_id}/ad-recommendations/{recommendation_id}/confirmation",
    response_model=AdRecommendationResponse,
)
def patch_ad_recommendation_confirmation(
    product_id: int,
    recommendation_id: int,
    payload: AdRecommendationConfirmation,
    request: Request,
    confirmer: AdConfirmer,
    session: DatabaseSession,
) -> dict:
    return confirm_ad_recommendation(
        session,
        product_id=product_id,
        recommendation_id=recommendation_id,
        payload=payload,
        actor=confirmer,
        request_id=request.state.request_id,
    )


@router.post(
    "/products/{product_id}/ad-experiments/generate",
    response_model=AdExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_ad_experiment_generate(
    product_id: int,
    payload: AdExperimentGenerateRequest,
    request: Request,
    writer: ExperimentWriter,
    session: DatabaseSession,
) -> dict:
    return generate_ad_experiment(
        session,
        product_id=product_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )


@router.get(
    "/products/{product_id}/ad-experiments",
    response_model=Page[AdExperimentResponse],
)
def get_ad_experiments(
    product_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
    experiment_status: Annotated[
        Literal["draft", "confirmed", "running", "finished", "cancelled"] | None,
        Query(alias="status"),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdExperimentResponse]:
    del current_user
    items, total = list_ad_experiments(
        session,
        product_id=product_id,
        status=experiment_status,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/products/{product_id}/ad-experiments/{experiment_id}",
    response_model=AdExperimentResponse,
)
def get_ad_experiment(
    product_id: int,
    experiment_id: int,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict:
    del current_user
    return _experiment_response(
        get_experiment_or_error(session, product_id=product_id, experiment_id=experiment_id)
    )


@router.patch(
    "/products/{product_id}/ad-experiments/{experiment_id}",
    response_model=AdExperimentResponse,
)
def patch_ad_experiment(
    product_id: int,
    experiment_id: int,
    payload: AdExperimentUpdate,
    request: Request,
    writer: ExperimentWriter,
    session: DatabaseSession,
) -> dict:
    return update_ad_experiment(
        session,
        product_id=product_id,
        experiment_id=experiment_id,
        payload=payload,
        actor=writer,
        request_id=request.state.request_id,
    )
