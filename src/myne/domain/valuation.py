from decimal import Decimal

from myne.domain.models import (
    Condition,
    MarketSegment,
    PriceReport,
    PriceStats,
    SegmentPrice,
    Valuation,
    ValuationBasis,
)
from myne.domain.money import quantize

_MIN_CONDITION_SAMPLES = 2


def build_valuation(
    report: PriceReport, condition: Condition, purchase_price: Decimal | None
) -> Valuation:
    """Pick the most specific observed price for the owner's condition.

    No condition multipliers are applied: if there are too few listings in the
    requested condition, the estimate widens to all resale conditions (then retail)
    and `basis` says so, instead of fabricating an adjusted number.
    """
    estimate, basis = _select_estimate(report, condition)
    gain = gain_percent = None
    if estimate is not None and purchase_price is not None:
        gain = quantize(estimate.median - purchase_price)
        if purchase_price > 0:
            gain_percent = round(float(gain / purchase_price * 100), 2)

    return Valuation(
        condition=condition,
        basis=basis,
        currency=report.currency,
        estimate=estimate,
        purchase_price=quantize(purchase_price) if purchase_price is not None else None,
        gain=gain,
        gain_percent=gain_percent,
    )


def _select_estimate(
    report: PriceReport, condition: Condition
) -> tuple[PriceStats | None, ValuationBasis]:
    resale = _segment(report, MarketSegment.RESALE)
    retail = _segment(report, MarketSegment.RETAIL)

    if resale is not None and condition is not Condition.UNKNOWN:
        stats = resale.by_condition.get(condition)
        if stats is not None and stats.sample_size >= _MIN_CONDITION_SAMPLES:
            return stats, ValuationBasis.CONDITION
    if condition is Condition.NEW and retail is not None:
        return retail.stats, ValuationBasis.RETAIL
    if resale is not None:
        return resale.stats, ValuationBasis.ALL_CONDITIONS
    if retail is not None:
        return retail.stats, ValuationBasis.RETAIL
    return None, ValuationBasis.NONE


def _segment(report: PriceReport, segment: MarketSegment) -> SegmentPrice | None:
    return next((s for s in report.current if s.segment is segment), None)
