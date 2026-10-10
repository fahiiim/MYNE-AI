from fastapi import APIRouter
from pydantic import BaseModel

from myne import __version__
from myne.api.dependencies import ContainerDep

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(LivenessResponse):
    integrations: dict[str, bool]


@router.get("/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    return LivenessResponse(status="ok", version=__version__)


@router.get("/ready", response_model=ReadinessResponse)
async def ready(container: ContainerDep) -> ReadinessResponse:
    return ReadinessResponse(
        status="ok", version=__version__, integrations=dict(container.integrations)
    )
