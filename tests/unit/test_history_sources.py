from datetime import date

import pytest

from myne.ai.schemas import PriceClaim, PriceClaimExtraction
from myne.domain.models import BagIdentity, MarketSegment
from myne.integrations.types import WebResult
from myne.services.pricing.history_sources import ReportedPriceHistorySource
from myne.services.pricing.sources import PriceQuery
from myne.services.pricing.window import DateWindow
from tests.fakes import ScriptedLLM

TODAY = date(2026, 10, 13)


@pytest.mark.parametrize(
    ("identity", "expected"),
    [
        (
            BagIdentity(brand="Hermès", model="Herbag Zip 31 (PM)", size="31 cm (PM)"),
            "Hermès Herbag Zip 31 PM",
        ),
        (
            BagIdentity(brand="Hermès", model="Herbag (general / Retourne variants)"),
            "Hermès Herbag general Retourne variants",
        ),
        (
            BagIdentity(brand="Chanel", model="Classic Flap", size="Medium"),
            "Chanel Classic Flap Medium",
        ),
    ],
)
def test_search_query_strips_brackets_separators_and_units(
    identity: BagIdentity, expected: str
) -> None:
    assert identity.search_query() == expected


class StubSerper:
    def __init__(self, results: list[WebResult]) -> None:
        self._results = results

    async def search(self, query: str, **_: object) -> list[WebResult]:
        return self._results

    async def news(self, query: str, **_: object) -> list[WebResult]:
        return []


async def test_retail_claims_from_resellers_are_counted_as_resale() -> None:
    snippets = [
        WebResult(
            title="Hermès Herbag Zip 31 price increase 2026",
            url="https://www.pursebop.com/hermes-price-increase-2026/",
            snippet="In May 2026 the Herbag Zip 31 rose to $3,525 in US boutiques.",
            date_text="May 12, 2026",
            source="PurseBop",
        ),
        WebResult(
            title="Hermes Herbag Zip 31 PM Toile",
            url="https://www.fashionphile.com/p/hermes-herbag-zip-31",
            snippet="Unused Herbag Zip 31 PM, now $2,095.",
            date_text="May 15, 2026",
            source="Fashionphile",
        ),
    ]
    llm = ScriptedLLM(
        {
            PriceClaimExtraction: PriceClaimExtraction(
                claims=[
                    PriceClaim(
                        snippet_id=0,
                        amount=3525,
                        currency="USD",
                        price_type="retail",
                        as_of_month="2026-05",
                        quote="rose to $3,525",
                    ),
                    PriceClaim(
                        snippet_id=1,
                        amount=2095,
                        currency="USD",
                        price_type="retail",
                        as_of_month=None,
                        quote="now $2,095",
                    ),
                ]
            )
        }
    )
    source = ReportedPriceHistorySource(serper=StubSerper(snippets), llm=llm)  # type: ignore[arg-type]
    identity = BagIdentity(brand="Hermès", model="Herbag Zip 31")

    prices = await source.collect(
        PriceQuery(
            identity=identity,
            window=DateWindow.trailing_months(TODAY, 6),
            today=TODAY,
            search_query=identity.search_query(),
        )
    )

    assert [(p.price.amount, p.segment_hint) for p in prices] == [
        (3525, MarketSegment.RETAIL),
        (2095, MarketSegment.RESALE),
    ]
