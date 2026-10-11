from typing import Annotated, cast

from fastapi import Depends, Request

from myne.container import Container
from myne.core.config import Settings
from myne.services.appraisal import BagAppraisalService


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]


def get_settings(container: ContainerDep) -> Settings:
    return container.settings


def get_appraisal_service(container: ContainerDep) -> BagAppraisalService:
    return container.appraisals


SettingsDep = Annotated[Settings, Depends(get_settings)]
AppraisalServiceDep = Annotated[BagAppraisalService, Depends(get_appraisal_service)]
