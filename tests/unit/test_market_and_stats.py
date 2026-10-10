from decimal import Decimal

import pytest

from myne.domain.market import classify_listing, normalize_condition
from myne.domain.models import Condition, MarketSegment
from myne.domain.stats import remove_outliers, summarize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pre-Owned", Condition.GOOD),
        ("Pre-owned - Like New", Condition.EXCELLENT),
        ("Very Good", Condition.EXCELLENT),
        ("Brand New", Condition.NEW),
        ("Unworn", Condition.NEW),
        ("Fair", Condition.FAIR),
        (None, Condition.UNKNOWN),
    ],
)
def test_normalize_condition(raw: str | None, expected: Condition) -> None:
    assert normalize_condition(raw) is expected


def test_resale_venue_detected_from_seller_name() -> None:
    segment, condition = classify_listing(condition_hint=None, seller="Fashionphile", url=None)
    assert (segment, condition) == (MarketSegment.RESALE, Condition.UNKNOWN)


def test_unknown_retail_listing_defaults_to_new() -> None:
    segment, condition = classify_listing(
        condition_hint=None, seller="Neiman Marcus", url="https://www.neimanmarcus.com/p/x"
    )
    assert (segment, condition) == (MarketSegment.RETAIL, Condition.NEW)


def test_remove_outliers_drops_accessory_priced_listings() -> None:
    values = [Decimal(v) for v in ("12000", "12500", "13000", "12800", "350")]
    assert Decimal("350") not in remove_outliers(values)


def test_summarize_single_value() -> None:
    stats = summarize([Decimal("9999.999")])
    assert stats is not None
    assert stats.median == stats.low == stats.high == Decimal("10000.00")


def test_summarize_empty() -> None:
    assert summarize([]) is None
