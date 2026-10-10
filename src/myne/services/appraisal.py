from myne.domain.models import Appraisal
from myne.services.contracts import BagIdentificationService, PriceReportService


class AppraisalService:
    """Identify, then price automatically only when the identification is unambiguous."""

    def __init__(self, *, identifier: BagIdentificationService, prices: PriceReportService) -> None:
        self._identifier = identifier
        self._prices = prices

    async def appraise(self, image: bytes, *, notes: str | None, currency: str) -> Appraisal:
        identification = await self._identifier.identify(image, notes=notes)
        if identification.needs_confirmation or not identification.candidates:
            return Appraisal(identification=identification, prices=None)
        report = await self._prices.report(identification.candidates[0].identity, currency=currency)
        return Appraisal(identification=identification, prices=report)
