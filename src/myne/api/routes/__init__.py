from fastapi import APIRouter

from myne.api.routes import analyze, health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(analyze.router)

__all__ = ["api_router", "health"]
