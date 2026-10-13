from decimal import Decimal

from myne.domain.models import AnalysisInput, AnalysisMode, BagIdentity, Condition
from myne.services.analysis import LENS_SOURCE, BagAnalysisService
from myne.services.progress import AnalysisStage
from tests.fakes import LENS_OFFER, StubIdentifier, StubImages, StubPrices

IMAGE_URL = "https://cdn.example.com/bag.jpg"


def _service(identifier: StubIdentifier | None = None) -> tuple[BagAnalysisService, StubPrices]:
    prices = StubPrices()
    service = BagAnalysisService(
        images=StubImages(),
        identifier=identifier or StubIdentifier(),
        prices=prices,
        default_currency="USD",
    )
    return service, prices


async def test_image_only_identifies_then_prices_with_lens_offers() -> None:
    service, prices = _service()
    stages: list[AnalysisStage] = []

    async def record(stage: AnalysisStage, payload: dict[str, object]) -> None:
        stages.append(stage)

    analysis = await service.analyze(AnalysisInput(image_url=IMAGE_URL), progress=record)

    assert analysis.mode is AnalysisMode.IMAGE
    assert analysis.bag is not None
    assert analysis.bag.model == "Neverfull"
    assert analysis.identification is not None
    assert analysis.valuation is not None
    assert analysis.valuation.condition is Condition.GOOD
    assert prices.calls[0]["extra_listings"] == {LENS_SOURCE: (LENS_OFFER,)}
    assert stages == [
        AnalysisStage.IMAGE_FETCHED,
        AnalysisStage.ATTRIBUTES_EXTRACTED,
        AnalysisStage.PRICING_STARTED,
        AnalysisStage.PRICING_COMPLETED,
    ]
    assert "Historical coverage is limited" in analysis.warnings[0]


async def test_caller_details_override_identified_fields_and_feed_the_identifier() -> None:
    identifier = StubIdentifier()
    service, _prices = _service(identifier)

    analysis = await service.analyze(
        AnalysisInput(
            image_url=IMAGE_URL,
            brand="LV",
            size="GM",
            color=["Black"],
            condition="Excellent",
            purchase_price=Decimal("1500"),
            currency="EUR",
            extra={"listing_title": "Neverfull GM Damier"},
        )
    )

    assert analysis.mode is AnalysisMode.IMAGE_WITH_DETAILS
    assert analysis.bag == BagIdentity(
        brand="LV", model="Neverfull", size="GM", material="Monogram canvas", color="Black"
    )
    assert analysis.currency == "EUR"
    assert analysis.valuation is not None
    assert analysis.valuation.condition is Condition.EXCELLENT
    assert analysis.valuation.purchase_price == Decimal("1500")
    request = identifier.requests[0]
    assert request.lens_query == "LV"
    assert request.notes is not None
    assert "brand: LV" in request.notes
    assert "Neverfull GM Damier" in request.notes


async def test_conflicting_brand_discards_identification_and_warns() -> None:
    service, _prices = _service()

    analysis = await service.analyze(
        AnalysisInput(image_url=IMAGE_URL, brand="Chanel", model="Boy")
    )

    assert analysis.bag == BagIdentity(brand="Chanel", model="Boy")
    assert any("differs from the details provided" in w for w in analysis.warnings)


async def test_details_only_skips_identification() -> None:
    identifier = StubIdentifier()
    service, prices = _service(identifier)

    analysis = await service.analyze(
        AnalysisInput(brand="Hermès", model="Birkin", search_query="hermes birkin 30 togo")
    )

    assert analysis.mode is AnalysisMode.DETAILS
    assert analysis.identification is None
    assert identifier.requests == []
    assert prices.calls[0]["search_query"] == "hermes birkin 30 togo"
    assert prices.calls[0]["extra_listings"] is None
    assert analysis.valuation is not None
    assert analysis.valuation.condition is Condition.UNKNOWN


async def test_unidentified_image_returns_identification_without_pricing() -> None:
    service, prices = _service(StubIdentifier(identity=None))

    analysis = await service.analyze(AnalysisInput(image_url=IMAGE_URL))

    assert analysis.bag is None
    assert analysis.valuation is None
    assert analysis.identification is not None
    assert analysis.market_prices == []
    assert analysis.price_history == []
    assert prices.calls == []
    assert any("could not be identified" in w for w in analysis.warnings)
