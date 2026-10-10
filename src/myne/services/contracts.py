from typing import Protocol

from myne.domain.models import BagIdentity, IdentificationResult, PriceReport


class BagIdentificationService(Protocol):
    async def identify(self, image: bytes, *, notes: str | None = None) -> IdentificationResult: ...


class PriceReportService(Protocol):
    async def report(self, identity: BagIdentity, *, currency: str) -> PriceReport: ...
