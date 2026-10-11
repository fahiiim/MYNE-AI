import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from myne.core.cache import TTLCache
from myne.core.errors import MyneError
from myne.domain.market import classify_listing
from myne.domain.matching import ListingMatcher
from myne.domain.models import (
    BagIdentity,
    Condition,
    MarketSegment,
    MatchQuality,
    MonthlyPricePoint,
    PriceObservation,
    PriceReport,
    PriceSeries,
    SegmentPrice,
    SourceStatus,
)
from myne.domain.money import quantize
from myne.domain.stats import summarize
from myne.domain.text import normalize_text
from myne.services.pricing.fx import CurrencyConverter
from myne.services.pricing.sources import PriceQuery, PriceSource, RawPrice
from myne.services.pricing.window import DateWindow, month_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PricingPolicy:
    history_months: int = 6
    cache_ttl_seconds: float = 6 * 3600
    source_timeout_seconds: float = 60.0
    min_exact_samples: int = 3
    listings_per_segment: int = 10


@dataclass(frozen=True, slots=True)
class _SourceOutcome:
    status: SourceStatus
    prices: list[RawPrice]


class MarketPriceService:
    """Fans out to every price source, then filters, normalizes and aggregates.

    Sources fail independently: a broken provider yields a SourceStatus with an
    error instead of failing the report. Reports are cached in-process only when
    at least one source succeeded.
    """

    def __init__(
        self,
        *,
        sources: Sequence[PriceSource],
        fx: CurrencyConverter,
        policy: PricingPolicy,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sources = tuple(sources)
        self._fx = fx
        self._policy = policy
        self._clock = clock
        self._cache: TTLCache[str, PriceReport] = TTLCache(
            ttl_seconds=policy.cache_ttl_seconds, max_entries=512
        )

    async def report(
        self, identity: BagIdentity, *, currency: str, search_query: str | None = None
    ) -> PriceReport:
        query_text = (search_query or "").strip() or identity.search_query()
        key = f"{identity.cache_key()}|{currency}|{normalize_text(query_text)}"
        if (cached := self._cache.get(key)) is not None:
            return cached
        report = await self._build(identity, currency, query_text)
        if any(status.ok for status in report.sources):
            self._cache.set(key, report)
        return report

    async def _build(self, identity: BagIdentity, currency: str, query_text: str) -> PriceReport:
        now = self._clock()
        query = PriceQuery(
            identity=identity,
            window=DateWindow.trailing_months(now.date(), self._policy.history_months),
            today=now.date(),
            search_query=query_text,
        )
        outcomes = await asyncio.gather(*(self._collect(s, query) for s in self._sources))

        warnings: list[str] = []
        raw = [price for outcome in outcomes for price in outcome.prices]
        observations = await self._normalize(raw, identity, currency, warnings)
        current = self._current(observations, warnings)
        history = self._history(observations, query.window)

        if not self._sources:
            warnings.append("No price sources are configured.")
        elif not observations:
            warnings.append("No listings matching this exact bag were found.")
        if history and max(series.months_with_data for series in history) <= 1:
            warnings.append("Historical coverage is limited; trend data may be incomplete.")

        return PriceReport(
            identity=identity,
            currency=currency,
            generated_at=now,
            current=current,
            history=history,
            sources=[outcome.status for outcome in outcomes],
            warnings=warnings,
        )

    async def _collect(self, source: PriceSource, query: PriceQuery) -> _SourceOutcome:
        try:
            async with asyncio.timeout(self._policy.source_timeout_seconds):
                prices = await source.collect(query)
        except TimeoutError:
            return _SourceOutcome(SourceStatus(name=source.name, ok=False, error="timed out"), [])
        except MyneError as exc:
            return _SourceOutcome(SourceStatus(name=source.name, ok=False, error=exc.detail), [])
        except Exception:
            # A parser bug in one provider must not take down the whole report.
            logger.exception("Price source crashed", extra={"ctx": {"source": source.name}})
            return _SourceOutcome(
                SourceStatus(name=source.name, ok=False, error="internal error"), []
            )
        return _SourceOutcome(SourceStatus(name=source.name, ok=True, results=len(prices)), prices)

    async def _normalize(
        self,
        raw: Sequence[RawPrice],
        identity: BagIdentity,
        currency: str,
        warnings: list[str],
    ) -> list[PriceObservation]:
        matcher = ListingMatcher(identity)
        fx_available = True
        unconvertible: set[str] = set()
        seen: set[tuple[str, str]] = set()
        observations: list[PriceObservation] = []

        for item in raw:
            match = MatchQuality.EXACT if item.prematched else matcher.evaluate(item.title)
            if match is None:
                continue

            amount = item.price.amount if item.price.currency == currency else None
            if amount is None and fx_available:
                try:
                    amount = await self._fx.convert(item.price, currency)
                except MyneError:
                    fx_available = False
                    warnings.append("Currency conversion unavailable; foreign prices omitted.")
            if amount is None:
                unconvertible.add(item.price.currency)
                continue

            dedupe_key = (item.url or f"{item.source}:{item.title}", item.observed_on.isoformat())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            segment, condition = classify_listing(
                condition_hint=item.condition_hint,
                seller=item.seller,
                url=item.url,
                segment_hint=item.segment_hint,
            )
            observations.append(
                PriceObservation(
                    source=item.source,
                    seller=item.seller,
                    segment=segment,
                    condition=condition,
                    match=match,
                    title=item.title,
                    url=item.url,
                    original_price=item.price,
                    amount=quantize(amount),
                    observed_on=item.observed_on,
                    live=item.live,
                )
            )

        if unconvertible and fx_available:
            warnings.append(f"Omitted prices in unsupported currencies: {sorted(unconvertible)}.")
        return observations

    def _current(
        self, observations: Sequence[PriceObservation], warnings: list[str]
    ) -> list[SegmentPrice]:
        segments: list[SegmentPrice] = []
        for segment in MarketSegment:
            matched = [o for o in observations if o.live and o.segment is segment]
            exact = [o for o in matched if o.match is MatchQuality.EXACT]
            basis = exact if len(exact) >= self._policy.min_exact_samples else matched
            stats = summarize([o.amount for o in basis])
            if stats is None:
                continue
            if basis is matched and len(exact) < len(matched):
                warnings.append(
                    f"Few exact-variant {segment.value} listings; figures include related sizes."
                )

            by_condition: dict[Condition, list[PriceObservation]] = defaultdict(list)
            for observation in basis:
                by_condition[observation.condition].append(observation)

            segments.append(
                SegmentPrice(
                    segment=segment,
                    stats=stats,
                    by_condition={
                        condition: condition_stats
                        for condition, group in by_condition.items()
                        if (condition_stats := summarize([o.amount for o in group])) is not None
                    },
                    listings=sorted(basis, key=lambda o: o.amount)[
                        : self._policy.listings_per_segment
                    ],
                )
            )
        return segments

    @staticmethod
    def _history(observations: Sequence[PriceObservation], window: DateWindow) -> list[PriceSeries]:
        series: list[PriceSeries] = []
        for segment in MarketSegment:
            buckets: dict[str, list[PriceObservation]] = defaultdict(list)
            for observation in observations:
                if observation.segment is segment and window.contains(observation.observed_on):
                    buckets[month_key(observation.observed_on)].append(observation)
            if not buckets:
                continue

            points = [
                MonthlyPricePoint(
                    month=month,
                    stats=summarize([o.amount for o in buckets.get(month, [])]),
                    sources=sorted({o.source for o in buckets.get(month, [])}),
                )
                for month in window.months()
            ]
            series.append(
                PriceSeries(
                    segment=segment,
                    months_with_data=sum(1 for point in points if point.stats is not None),
                    points=points,
                )
            )
        return series
