from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from myne.domain.models import BagIdentity, IdentificationResult, PriceReport
from myne.integrations.types import MarketListing
from myne.services.progress import ProgressCallback


@dataclass(frozen=True, slots=True)
class IdentificationRequest:
    image: bytes
    notes: str | None = None
    image_url: str | None = None
    lens_query: str | None = None


@dataclass(frozen=True, slots=True)
class Identification:
    result: IdentificationResult
    lens_offers: tuple[MarketListing, ...] = ()


class BagIdentificationService(Protocol):
    async def identify(
        self, request: IdentificationRequest, *, progress: ProgressCallback | None = None
    ) -> Identification: ...


class PriceReportService(Protocol):
    async def report(
        self,
        identity: BagIdentity,
        *,
        currency: str,
        search_query: str | None = None,
        extra_listings: Mapping[str, Sequence[MarketListing]] | None = None,
    ) -> PriceReport: ...


class ImageSource(Protocol):
    async def fetch(self, url: str) -> bytes: ...
