from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from myne.domain.models import BagIdentity, MarketSegment, Money
from myne.integrations.serpapi import SerpApiClient
from myne.integrations.serper import SerperClient
from myne.integrations.types import MarketListing
from myne.services.pricing.window import DateWindow


@dataclass(frozen=True, slots=True)
class PriceQuery:
    identity: BagIdentity
    window: DateWindow
    today: date
    search_query: str


@dataclass(frozen=True, slots=True)
class RawPrice:
    source: str
    title: str
    url: str | None
    seller: str | None
    price: Money
    observed_on: date
    live: bool
    condition_hint: str | None = None
    segment_hint: MarketSegment | None = None
    prematched: bool = False


class PriceSource(Protocol):
    name: str

    async def collect(self, query: PriceQuery) -> list[RawPrice]: ...


def live_prices(source: str, listings: Iterable[MarketListing], today: date) -> list[RawPrice]:
    return [
        RawPrice(
            source=source,
            title=listing.title,
            url=listing.url,
            seller=listing.seller,
            price=price,
            observed_on=today,
            live=True,
            condition_hint=listing.condition_hint,
        )
        for listing in listings
        if (price := listing.price) is not None
    ]


class GoogleShoppingSource:
    name = "google_shopping"

    def __init__(self, serpapi: SerpApiClient) -> None:
        self._serpapi = serpapi

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        listings = await self._serpapi.google_shopping(query.search_query)
        return live_prices(self.name, listings, query.today)


class EbayListingsSource:
    name = "ebay"

    def __init__(self, serpapi: SerpApiClient) -> None:
        self._serpapi = serpapi

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        listings = await self._serpapi.ebay(query.search_query)
        return live_prices(self.name, listings, query.today)


class SerperShoppingSource:
    name = "serper_shopping"

    def __init__(self, serper: SerperClient) -> None:
        self._serper = serper

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        listings = await self._serper.shopping(query.search_query)
        return live_prices(self.name, listings, query.today)
