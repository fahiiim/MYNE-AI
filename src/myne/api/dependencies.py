from typing import Annotated, cast

from fastapi import Depends, Request

from myne.container import Container
from myne.core.config import Settings
from myne.services.appraisal import AppraisalService
from myne.services.contracts import BagIdentificationService, PriceReportService


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]


def get_settings(container: ContainerDep) -> Settings:
    return container.settings


def get_identifier(container: ContainerDep) -> BagIdentificationService:
    return container.identifier


def get_price_service(container: ContainerDep) -> PriceReportService:
    return container.prices


def get_appraisal_service(container: ContainerDep) -> AppraisalService:
    return container.appraisals


SettingsDep = Annotated[Settings, Depends(get_settings)]
IdentifierDep = Annotated[BagIdentificationService, Depends(get_identifier)]
PriceServiceDep = Annotated[PriceReportService, Depends(get_price_service)]
AppraisalServiceDep = Annotated[AppraisalService, Depends(get_appraisal_service)]
