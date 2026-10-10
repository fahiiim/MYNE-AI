import asyncio
from decimal import Decimal
from typing import Protocol

from myne.core.cache import TTLCache
from myne.core.errors import UpstreamServiceError
from myne.core.http import HttpClient
from myne.domain.models import Money


class CurrencyConverter(Protocol):
    async def convert(self, money: Money, target: str) -> Decimal | None: ...


class FrankfurterFx:
    """ECB reference rates via the free Frankfurter API, cached in-process."""

    _SERVICE = "fx"

    def __init__(self, http: HttpClient, *, rates_url: str, ttl_seconds: float = 12 * 3600) -> None:
        self._http = http
        self._rates_url = rates_url
        self._cache: TTLCache[str, dict[str, Decimal]] = TTLCache(
            ttl_seconds=ttl_seconds, max_entries=32
        )
        self._lock = asyncio.Lock()

    async def convert(self, money: Money, target: str) -> Decimal | None:
        if money.currency == target:
            return money.amount
        rate = (await self._rates(target)).get(money.currency)
        return money.amount / rate if rate else None

    async def _rates(self, base: str) -> dict[str, Decimal]:
        if (cached := self._cache.get(base)) is not None:
            return cached
        async with self._lock:
            if (cached := self._cache.get(base)) is not None:
                return cached
            payload = await self._http.request_json(
                self._SERVICE, "GET", self._rates_url, params={"base": base}
            )
            raw_rates = payload.get("rates") if isinstance(payload, dict) else None
            if not isinstance(raw_rates, dict):
                raise UpstreamServiceError(self._SERVICE, "rates missing from response")
            rates = {code: Decimal(str(value)) for code, value in raw_rates.items()}
            self._cache.set(base, rates)
            return rates
