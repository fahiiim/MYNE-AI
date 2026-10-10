from fastapi import APIRouter

from myne.api.routes import appraisals, health, identifications, price_reports

api_router = APIRouter(prefix="/v1")
api_router.include_router(identifications.router)
api_router.include_router(price_reports.router)
api_router.include_router(appraisals.router)

__all__ = ["api_router", "health"]
