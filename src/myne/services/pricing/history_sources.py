"""Dated price sources that work without a database.

* WaybackRetailHistorySource: monthly Internet Archive snapshots of retailer
  product pages, parsed deterministically (JSON-LD / meta tags).
* ReportedPriceHistorySource: dated web/news snippets (price increases, resale
  reports) read by an LLM; every claim must quote the snippet verbatim or it is
  discarded.
"""

import asyncio
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from myne.ai import prompts
from myne.ai.llm import StructuredLLM
from myne.ai.schemas import PriceClaim, PriceClaimExtraction
from myne.core.errors import MyneError
from myne.domain.market import RETAIL_HOSTS, host_in
from myne.domain.matching import ListingMatcher
from myne.domain.models import BagIdentity, MarketSegment, Money
from myne.integrations.serper import SerperClient
from myne.integrations.types import ArchiveSnapshot, WebResult
from myne.integrations.wayback import WaybackClient
from myne.services.pricing.dates import parse_month, parse_published
from myne.services.pricing.html_price import extract_product_price
from myne.services.pricing.sources import PriceQuery, RawPrice

logger = logging.getLogger(__name__)


class WaybackRetailHistorySource:
    name = "wayback_retail"

    def __init__(
        self,
        *,
        serper: SerperClient,
        wayback: WaybackClient,
        max_pages: int,
        concurrency: int = 4,
    ) -> None:
        self._serper = serper
        self._wayback = wayback
        self._max_pages = max_pages
        self._concurrency = concurrency

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        pages = await self._product_pages(query.identity)
        semaphore = asyncio.Semaphore(self._concurrency)
        batches = await asyncio.gather(*(self._page_history(p, query, semaphore) for p in pages))
        return [price for batch in batches for price in batch]

    async def _product_pages(self, identity: BagIdentity) -> list[WebResult]:
        if self._max_pages == 0:
            return []
        results = await self._serper.search(f"{identity.search_query()} price", num=20)
        matcher = ListingMatcher(identity)
        pages = [
            result
            for result in results
            if host_in(result.url, RETAIL_HOSTS) and matcher.evaluate(result.title) is not None
        ]
        return pages[: self._max_pages]

    async def _page_history(
        self, page: WebResult, query: PriceQuery, semaphore: asyncio.Semaphore
    ) -> list[RawPrice]:
        try:
            async with semaphore:
                snapshots = await self._wayback.monthly_snapshots(
                    page.url, start=query.window.start, end=query.window.end
                )
        except MyneError as exc:
            logger.info("Wayback CDX lookup failed", extra={"ctx": {"error": exc.detail}})
            return []

        prices = await asyncio.gather(
            *(self._snapshot_price(page, snapshot, semaphore) for snapshot in snapshots)
        )
        return [price for price in prices if price is not None]

    async def _snapshot_price(
        self, page: WebResult, snapshot: ArchiveSnapshot, semaphore: asyncio.Semaphore
    ) -> RawPrice | None:
        try:
            async with semaphore:
                html = await self._wayback.fetch_html(snapshot)
        except MyneError:
            return None
        money = await asyncio.to_thread(extract_product_price, html)
        if money is None:
            return None
        return RawPrice(
            source=self.name,
            title=page.title,
            url=page.url,
            seller=page.source,
            price=money,
            observed_on=snapshot.captured_on,
            live=False,
            condition_hint="new",
            segment_hint=MarketSegment.RETAIL,
            prematched=True,
        )


class ReportedPriceHistorySource:
    name = "web_reports"
    _MAX_SNIPPETS = 24

    def __init__(self, *, serper: SerperClient, llm: StructuredLLM) -> None:
        self._serper = serper
        self._llm = llm

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        snippets = await self._snippets(query)
        if not snippets:
            return []

        rendered = [
            (sid, s.title, s.snippet, d.isoformat() if (d := self._published(s, query)) else None)
            for sid, s in enumerate(snippets)
        ]
        extraction = await self._llm.generate(
            system=prompts.PRICE_CLAIMS_SYSTEM,
            prompt=prompts.price_claims_prompt(query.identity, rendered, query.today),
            schema=PriceClaimExtraction,
        )

        prices: list[RawPrice] = []
        for claim in extraction.claims:
            if not 0 <= claim.snippet_id < len(snippets):
                continue
            snippet = snippets[claim.snippet_id]
            if price := self._to_price(claim, snippet, query):
                prices.append(price)
        return prices

    async def _snippets(self, query: PriceQuery) -> list[WebResult]:
        identity = query.identity
        base = f"{identity.brand} {identity.model}"
        tbs = f"qdr:m{query.window.span_in_months}"
        requests = (
            self._serper.search(f"{base} price increase", tbs=tbs),
            self._serper.search(f"{identity.search_query()} retail price", tbs=tbs),
            self._serper.search(f"{identity.search_query()} resale price", tbs=tbs),
            self._serper.news(f"{base} price", tbs=tbs),
        )
        batches = await asyncio.gather(*requests, return_exceptions=True)
        failures = [b for b in batches if isinstance(b, BaseException)]
        if len(failures) == len(batches):
            raise failures[0]

        seen: set[str] = set()
        snippets: list[WebResult] = []
        for batch in batches:
            if isinstance(batch, BaseException):
                continue
            for result in batch:
                if result.snippet and result.url not in seen:
                    seen.add(result.url)
                    snippets.append(result)
        return snippets[: self._MAX_SNIPPETS]

    @staticmethod
    def _published(snippet: WebResult, query: PriceQuery) -> date | None:
        return parse_published(snippet.date_text, today=query.today)

    def _to_price(
        self, claim: PriceClaim, snippet: WebResult, query: PriceQuery
    ) -> RawPrice | None:
        if not _is_grounded(claim, snippet):
            return None
        observed_on = parse_month(claim.as_of_month) or self._published(snippet, query)
        if observed_on is None or not query.window.contains(observed_on):
            return None
        try:
            money = Money(amount=Decimal(str(claim.amount)), currency=claim.currency)
        except (ValidationError, InvalidOperation):
            return None

        is_retail = claim.price_type == "retail"
        return RawPrice(
            source=self.name,
            title=snippet.title,
            url=snippet.url,
            seller=snippet.source,
            price=money,
            observed_on=observed_on,
            live=False,
            condition_hint="new" if is_retail else None,
            segment_hint=MarketSegment.RETAIL if is_retail else MarketSegment.RESALE,
            prematched=True,
        )


def _squash(text: str) -> str:
    return " ".join(text.casefold().split())


def _is_grounded(claim: PriceClaim, snippet: WebResult) -> bool:
    """The quote must appear verbatim in the snippet and contain the claimed figure."""
    quote = _squash(claim.quote)
    if not quote or quote not in _squash(f"{snippet.title} {snippet.snippet}"):
        return False
    if claim.amount <= 0:
        return False
    return str(int(claim.amount)) in re.sub(r"\D", "", claim.quote)
