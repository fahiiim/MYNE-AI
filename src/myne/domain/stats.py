from collections.abc import Sequence
from decimal import Decimal
from statistics import quantiles

from myne.domain.models import PriceStats
from myne.domain.money import quantize

_IQR_FENCE = Decimal("1.5")
_MIN_SAMPLES_FOR_OUTLIER_FILTER = 4


def remove_outliers(values: Sequence[Decimal]) -> list[Decimal]:
    ordered = sorted(values)
    if len(ordered) < _MIN_SAMPLES_FOR_OUTLIER_FILTER:
        return ordered
    q1, _, q3 = quantiles(ordered, n=4, method="inclusive")
    fence = (q3 - q1) * _IQR_FENCE
    return [v for v in ordered if q1 - fence <= v <= q3 + fence]


def summarize(values: Sequence[Decimal]) -> PriceStats | None:
    clean = remove_outliers(values)
    if not clean:
        return None
    if len(clean) == 1:
        p25 = mid = p75 = clean[0]
    else:
        p25, mid, p75 = quantiles(clean, n=4, method="inclusive")
    return PriceStats(
        sample_size=len(clean),
        median=quantize(mid),
        p25=quantize(p25),
        p75=quantize(p75),
        low=quantize(clean[0]),
        high=quantize(clean[-1]),
    )
