from decimal import Decimal

from myne.domain.market import normalize_condition
from myne.domain.models import (
    BagAppraisal,
    BagIdentity,
    Condition,
    IdentificationResult,
    ImageAppraisal,
)
from myne.domain.valuation import build_valuation
from myne.services.contracts import (
    BagIdentificationService,
    IdentificationRequest,
    ImageSource,
    PriceReportService,
)
from myne.services.progress import IdentificationStage, ProgressCallback, emit


class BagAppraisalService:
    """Application facade behind the public API: identify, price, value."""

    def __init__(
        self,
        *,
        images: ImageSource,
        identifier: BagIdentificationService,
        prices: PriceReportService,
        currency: str,
    ) -> None:
        self._images = images
        self._identifier = identifier
        self._prices = prices
        self._currency = currency

    async def identify_url(
        self,
        image_url: str,
        *,
        search_hint: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> IdentificationResult:
        image = await self._images.fetch(image_url)
        await emit(progress, IdentificationStage.IMAGE_FETCHED, {"bytes": len(image)})
        request = IdentificationRequest(
            image=image,
            image_url=image_url,
            lens_query=search_hint,
            notes=f"Owner's search hint: {search_hint}" if search_hint else None,
        )
        return await self._identifier.identify(request, progress=progress)

    async def price_by_image(
        self,
        image_url: str,
        *,
        search_hint: str | None,
        purchase_price: Decimal | None,
    ) -> ImageAppraisal:
        identification = await self.identify_url(image_url, search_hint=search_hint)
        if not identification.candidates:
            return ImageAppraisal(
                identification=identification, bag=None, valuation=None, report=None
            )

        bag = identification.candidates[0].identity
        condition = normalize_condition(identification.attributes.apparent_condition)
        report = await self._prices.report(bag, currency=self._currency)
        return ImageAppraisal(
            identification=identification,
            bag=bag,
            valuation=build_valuation(report, condition, purchase_price),
            report=report,
        )

    async def price_bag(
        self,
        bag: BagIdentity,
        *,
        condition: Condition,
        purchase_price: Decimal | None,
        search_query: str | None,
    ) -> BagAppraisal:
        report = await self._prices.report(bag, currency=self._currency, search_query=search_query)
        return BagAppraisal(
            bag=bag,
            valuation=build_valuation(report, condition, purchase_price),
            report=report,
        )
