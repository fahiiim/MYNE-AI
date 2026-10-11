from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from myne.api.schemas import BagPriceRequest
from myne.domain.models import (
    BagIdentity,
    Condition,
    MarketSegment,
    PriceReport,
    PriceStats,
    SegmentPrice,
    ValuationBasis,
)
from myne.domain.valuation import build_valuation

IDENTITY = BagIdentity(brand="Chanel", model="Classic Double Flap", size="Medium")


def _stats(median: str, sample_size: int = 5) -> PriceStats:
    value = Decimal(median)
    return PriceStats(
        sample_size=sample_size, median=value, p25=value, p75=value, low=value, high=value
    )


def _report(*segments: SegmentPrice) -> PriceReport:
    return PriceReport(
        identity=IDENTITY,
        currency="USD",
        generated_at=datetime(2026, 10, 11, tzinfo=UTC),
        current=list(segments),
        history=[],
        sources=[],
        warnings=[],
    )


RESALE = SegmentPrice(
    segment=MarketSegment.RESALE,
    stats=_stats("9000"),
    by_condition={
        Condition.EXCELLENT: _stats("9500", sample_size=3),
        Condition.FAIR: _stats("6000", sample_size=1),
    },
    listings=[],
)
RETAIL = SegmentPrice(
    segment=MarketSegment.RETAIL, stats=_stats("11300"), by_condition={}, listings=[]
)


def test_uses_condition_specific_resale_price_and_computes_gain() -> None:
    valuation = build_valuation(_report(RESALE, RETAIL), Condition.EXCELLENT, Decimal("8000"))
    assert valuation.basis is ValuationBasis.CONDITION
    assert valuation.estimate is not None
    assert valuation.estimate.median == Decimal("9500")
    assert valuation.gain == Decimal("1500.00")
    assert valuation.gain_percent == 18.75


def test_thin_condition_sample_widens_to_all_resale() -> None:
    valuation = build_valuation(_report(RESALE, RETAIL), Condition.FAIR, None)
    assert valuation.basis is ValuationBasis.ALL_CONDITIONS
    assert valuation.gain is None


def test_new_condition_without_resale_sample_uses_retail() -> None:
    valuation = build_valuation(_report(RESALE, RETAIL), Condition.NEW, None)
    assert valuation.basis is ValuationBasis.RETAIL


def test_no_market_data() -> None:
    valuation = build_valuation(_report(), Condition.GOOD, Decimal("100"))
    assert (valuation.basis, valuation.estimate, valuation.gain) == (
        ValuationBasis.NONE,
        None,
        None,
    )


def test_bag_price_request_maps_backend_contract() -> None:
    body = BagPriceRequest.model_validate(
        {
            "brand": "Hermès",
            "model": "Kelly",
            "condition": "Very Good",
            "color": "Noir",
            "leather": "Epsom",
            "size": "28",
            "special_variant": "Standard",
            "purchase_price": 12000,
        }
    )
    identity = body.to_identity()
    assert identity.color == "Noir"
    assert identity.material == "Epsom"
    assert identity.variant is None
    assert identity.hardware is None
    assert body.purchase_price_decimal == Decimal("12000")


def test_bag_price_request_accepts_color_list_and_special_variant() -> None:
    body = BagPriceRequest.model_validate(
        {
            "brand": "Hermès",
            "model": "Birkin",
            "condition": "New",
            "color": ["Gris", "Blanc"],
            "special_variant": "Himalaya",
        }
    )
    identity = body.to_identity()
    assert identity.color == "Gris / Blanc"
    assert identity.variant == "Himalaya"


def test_bag_price_request_requires_condition() -> None:
    with pytest.raises(ValidationError):
        BagPriceRequest.model_validate({"brand": "Chanel", "model": "Boy"})
