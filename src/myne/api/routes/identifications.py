from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from myne.api.dependencies import IdentifierDep, SettingsDep
from myne.api.uploads import read_image_upload
from myne.domain.models import IdentificationResult

router = APIRouter(prefix="/identifications", tags=["identification"])


@router.post(
    "",
    response_model=IdentificationResult,
    summary="Identify a handbag's brand and model from a photo",
)
async def create_identification(
    identifier: IdentifierDep,
    settings: SettingsDep,
    image: Annotated[UploadFile, File(description="JPEG, PNG or WebP photo of the bag.")],
    notes: Annotated[
        str | None,
        Form(max_length=2000, description="Optional details from the owner (brand, year, size)."),
    ] = None,
) -> IdentificationResult:
    payload = await read_image_upload(image, max_bytes=settings.max_upload_bytes)
    return await identifier.identify(payload, notes=notes)
