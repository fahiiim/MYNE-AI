from typing import Annotated, cast

from fastapi import Depends, Request

from myne.container import Container
from myne.core.config import Settings
from myne.services.analysis import BagAnalysisService


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]


def get_settings(container: ContainerDep) -> Settings:
    return container.settings


def get_analysis_service(container: ContainerDep) -> BagAnalysisService:
    return container.analysis


SettingsDep = Annotated[Settings, Depends(get_settings)]
AnalysisServiceDep = Annotated[BagAnalysisService, Depends(get_analysis_service)]
