from datetime import UTC, date, datetime
from decimal import Decimal

from myne.core.errors import UpstreamServiceError
from myne.domain.models import BagIdentity, MarketSegment, Money
from myne.services.pricing.service import MarketPriceService, PricingPolicy
from myne.services.pricing.sources import RawPrice
from tests.fakes import FailingSource, FixedRateFx, StaticSource

NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)
IDENTITY = BagIdentity(brand="Chanel", model="Classic Double Flap", size="Medium")


def _listing(
    title: str, amount: str, currency: str = "USD", *, seller: str = "Fashionphile"
) -> RawPrice:
    return RawPrice(
        source="google_shopping",
        title=title,
        url=f"https://example.com/{title.replace(' ', '-')}-{amount}",
        seller=seller,
        price=Money(amount=Decimal(amount), currency=currency),
        observed_on=NOW.date(),
        live=True,
        condition_hint="Excellent",
    )


def _retail_snapshot(on: date, amount: str) -> RawPrice:
    return RawPrice(
        source="wayback_retail",
        title="Classic Handbag",
        url="https://www.chanel.com/us/fashion/p/A01112/",
        seller="chanel.com",
        price=Money(amount=Decimal(amount), currency="USD"),
        observed_on=on,
        live=False,
        segment_hint=MarketSegment.RETAIL,
        condition_hint="new",
        prematched=True,
    )


def _service(*sources: object) -> MarketPriceService:
    return MarketPriceService(
        sources=sources,  # type: ignore[arg-type]
        fx=FixedRateFx({"EUR": Decimal("1.10")}),
        policy=PricingPolicy(history_months=6, min_exact_samples=2),
        clock=lambda: NOW,
    )


async def test_report_aggregates_filters_and_converts() -> None:
    live = StaticSource(
        "google_shopping",
        [
            _listing("Chanel Classic Double Flap Medium Caviar", "9800"),
            _listing("Chanel Classic Double Flap Medium Lambskin", "10200"),
            _listing("Chanel Classic Double Flap Medium Beige", "9000", "EUR"),
            _listing("Chanel Classic Double Flap Jumbo", "11000"),
            _listing("Chanel Classic Double Flap dust bag", "150"),
            _listing("Gucci Horsebit 1955", "2500"),
        ],
    )
    archive = StaticSource(
        "wayback_retail",
        [_retail_snapshot(date(2026, 5, 3), "10800"), _retail_snapshot(date(2026, 9, 2), "11300")],
    )
    broken = FailingSource("ebay", UpstreamServiceError("serpapi", "HTTP 429", status=429))

    report = await _service(live, archive, broken).report(IDENTITY, currency="USD")

    resale = next(s for s in report.current if s.segment is MarketSegment.RESALE)
    assert resale.stats.sample_size == 3
    assert resale.stats.median == Decimal("9900.00")
    assert {o.match.value for o in resale.listings} == {"exact"}

    retail_history = next(s for s in report.history if s.segment is MarketSegment.RETAIL)
    assert retail_history.months_with_data == 2
    assert retail_history.points[0].month == "2026-04"
    assert len(retail_history.points) == 7

    statuses = {s.name: s for s in report.sources}
    assert statuses["ebay"].ok is False
    assert statuses["ebay"].error == "serpapi: HTTP 429"


async def test_reports_are_cached_only_when_a_source_succeeds() -> None:
    failing = FailingSource("ebay", UpstreamServiceError("serpapi", "down"))
    service = _service(failing)

    first = await service.report(IDENTITY, currency="USD")
    second = await service.report(IDENTITY, currency="USD")

    assert first is not second
    assert first.current == []
    assert any("No listings" in warning for warning in first.warnings)
