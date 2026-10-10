from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from myne.api.dependencies import AppraisalServiceDep, SettingsDep
from myne.api.uploads import read_image_upload
from myne.domain.models import Appraisal, CurrencyCode

router = APIRouter(prefix="/appraisals", tags=["appraisal"])


@router.post(
    "",
    response_model=Appraisal,
    summary="Identify a bag and, when unambiguous, price it in one call",
)
async def create_appraisal(
    appraisals: AppraisalServiceDep,
    settings: SettingsDep,
    image: Annotated[UploadFile, File(description="JPEG, PNG or WebP photo of the bag.")],
    notes: Annotated[str | None, Form(max_length=2000)] = None,
    currency: Annotated[CurrencyCode | None, Form()] = None,
) -> Appraisal:
    payload = await read_image_upload(image, max_bytes=settings.max_upload_bytes)
    return await appraisals.appraise(
        payload, notes=notes, currency=currency or settings.default_currency
    )
