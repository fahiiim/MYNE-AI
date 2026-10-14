from fastapi import APIRouter

from myne.api.routes import bags, health, identify

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(identify.router)
api_router.include_router(bags.router)

__all__ = ["api_router", "health"]
