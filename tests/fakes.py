from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel

from myne.ai.llm import Effort, ImageInput
from myne.core.errors import ImageFetchError
from myne.domain.models import (
    BagAttributes,
    BagCandidate,
    BagIdentity,
    IdentificationResult,
    Money,
    PriceReport,
)
from myne.integrations.types import MarketListing
from myne.services.contracts import Identification, IdentificationRequest
from myne.services.pricing.sources import PriceQuery, RawPrice
from myne.services.progress import AnalysisStage, ProgressCallback, emit


class ScriptedLLM:
    """Returns a pre-built response per requested schema and records every call."""

    name = "scripted"

    def __init__(self, responses: dict[type[BaseModel], BaseModel]) -> None:
        self._responses = responses
        self.calls: list[type[BaseModel]] = []

    async def generate[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        images: Sequence[ImageInput] = (),
        effort: Effort = Effort.DEFAULT,
    ) -> T:
        self.calls.append(schema)
        response = self._responses[schema]
        assert isinstance(response, schema)
        return response

    async def aclose(self) -> None:
        return None


class StaticSource:
    def __init__(self, name: str, prices: list[RawPrice]) -> None:
        self.name = name
        self._prices = prices

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        return self._prices


class FailingSource:
    def __init__(self, name: str, error: Exception) -> None:
        self.name = name
        self._error = error

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        raise self._error


class FixedRateFx:
    def __init__(self, rates_to_target: dict[str, Decimal]) -> None:
        self._rates = rates_to_target

    async def convert(self, money: Money, target: str) -> Decimal | None:
        if money.currency == target:
            return money.amount
        rate = self._rates.get(money.currency)
        return money.amount * rate if rate is not None else None


NEVERFULL = BagIdentity(
    brand="Louis Vuitton", model="Neverfull", size="MM", material="Monogram canvas"
)
LENS_OFFER = MarketListing(
    title="Louis Vuitton Neverfull MM Monogram",
    url="https://www.fashionphile.com/p/neverfull-mm",
    seller="Fashionphile",
    price=Money(amount=Decimal("1450"), currency="USD"),
    condition_hint=None,
)


class StubImages:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.urls: list[str] = []

    async def fetch(self, url: str) -> bytes:
        self.urls.append(url)
        if self._fail:
            raise ImageFetchError("Image URL returned HTTP 404")
        return b"image-bytes"


class StubIdentifier:
    def __init__(self, identity: BagIdentity | None = NEVERFULL) -> None:
        self._identity = identity
        self.requests: list[IdentificationRequest] = []

    async def identify(
        self, request: IdentificationRequest, *, progress: ProgressCallback | None = None
    ) -> Identification:
        self.requests.append(request)
        await emit(progress, AnalysisStage.ATTRIBUTES_EXTRACTED, {"attributes": {}})
        candidates = (
            [BagCandidate(identity=self._identity, confidence=0.93, rationale="ok", evidence=[])]
            if self._identity
            else []
        )
        result = IdentificationResult(
            image_sha256="abc",
            attributes=BagAttributes(
                is_handbag=True,
                brand=self._identity.brand if self._identity else None,
                model_family=self._identity.model if self._identity else None,
                size=None,
                material=None,
                color="Brown",
                hardware=None,
                apparent_condition="good",
                distinctive_features=[],
                visible_text=[],
                confidence=0.9,
            ),
            candidates=candidates,
            needs_confirmation=not candidates,
            warnings=[],
        )
        return Identification(result, (LENS_OFFER,) if self._identity else ())


class StubPrices:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def report(
        self,
        identity: BagIdentity,
        *,
        currency: str,
        search_query: str | None = None,
        extra_listings: Mapping[str, Sequence[MarketListing]] | None = None,
    ) -> PriceReport:
        self.calls.append(
            {
                "identity": identity,
                "currency": currency,
                "search_query": search_query,
                "extra_listings": extra_listings,
            }
        )
        return PriceReport(
            identity=identity,
            currency=currency,
            generated_at=datetime(2026, 10, 11, tzinfo=UTC),
            current=[],
            history=[],
            sources=[],
            warnings=["Historical coverage is limited; trend data may be incomplete."],
        )
