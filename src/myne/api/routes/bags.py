from fastapi import APIRouter

from myne.api.dependencies import AppraisalServiceDep
from myne.api.schemas import BagPriceRequest, ImagePriceRequest
from myne.domain.market import normalize_condition
from myne.domain.models import BagAppraisal, ImageAppraisal

router = APIRouter(prefix="/bags", tags=["pricing"])


@router.post(
    "/price/by-image",
    response_model=ImageAppraisal,
    summary="Identify a bag from an image URL and value its top candidate",
)
async def price_by_image(
    body: ImagePriceRequest, appraisals: AppraisalServiceDep
) -> ImageAppraisal:
    return await appraisals.price_by_image(
        str(body.image_url),
        search_hint=body.image_search_query or None,
        purchase_price=body.purchase_price_decimal,
    )


@router.post(
    "/price",
    response_model=BagAppraisal,
    summary="Current market value and price history for a described bag",
)
async def price_bag(body: BagPriceRequest, appraisals: AppraisalServiceDep) -> BagAppraisal:
    return await appraisals.price_bag(
        body.to_identity(),
        condition=normalize_condition(body.condition),
        purchase_price=body.purchase_price_decimal,
        search_query=body.image_search_query,
    )
