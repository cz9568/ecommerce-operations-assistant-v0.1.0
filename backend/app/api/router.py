from fastapi import APIRouter

from backend.app.api.routes import (
    assets,
    auth,
    competitors,
    creative_plans,
    dashboard,
    demo_data,
    diagnoses,
    generation_jobs,
    health,
    imports,
    inventory,
    inventory_advice,
    marketing,
    performance,
    platform_accounts,
    products,
    settings,
    skus,
    stores,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(assets.router)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(stores.router)
api_router.include_router(platform_accounts.router)
api_router.include_router(products.router)
api_router.include_router(skus.router)
api_router.include_router(settings.router)
api_router.include_router(inventory.router)
api_router.include_router(inventory_advice.router)
api_router.include_router(imports.router)
api_router.include_router(competitors.router)
api_router.include_router(diagnoses.router)
api_router.include_router(creative_plans.router)
api_router.include_router(dashboard.router)
api_router.include_router(demo_data.router)
api_router.include_router(generation_jobs.router)
api_router.include_router(marketing.router)
api_router.include_router(performance.router)
