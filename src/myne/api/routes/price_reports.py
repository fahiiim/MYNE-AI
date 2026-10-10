from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from myne.api.dependencies import PriceServiceDep, SettingsDep
from myne.domain.models import BagIdentity, CurrencyCode, PriceReport

router = APIRouter(prefix="/price-reports", tags=["pricing"])


class PriceReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: BagIdentity
    currency: CurrencyCode | None = None


@router.post(
    "",
    response_model=PriceReport,
    summary="Current market price and monthly history for a confirmed bag",
)
async def create_price_report(
    body: PriceReportRequest, prices: PriceServiceDep, settings: SettingsDep
) -> PriceReport:
    return await prices.report(body.identity, currency=body.currency or settings.default_currency)
