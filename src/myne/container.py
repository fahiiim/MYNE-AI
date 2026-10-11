"""Composition root: the only place that knows which concrete adapters exist."""

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from functools import partial

import httpx

from myne import __version__
from myne.ai.gemini_llm import GeminiLLM
from myne.ai.llm import FallbackLLM, StructuredLLM
from myne.ai.openai_llm import OpenAILLM
from myne.core.config import Settings, secret_value
from myne.core.errors import ConfigurationError
from myne.core.http import HttpClient
from myne.domain.money import currency_for_country
from myne.integrations.google_vision import GoogleVisionClient
from myne.integrations.image_fetcher import ImageFetcher
from myne.integrations.serpapi import SerpApiClient
from myne.integrations.serper import SerperClient
from myne.integrations.wayback import WaybackClient
from myne.services.appraisal import BagAppraisalService
from myne.services.identification import BagIdentifier, IdentificationPolicy
from myne.services.images import ImagePreprocessor
from myne.services.pricing.fx import FrankfurterFx
from myne.services.pricing.history_sources import (
    ReportedPriceHistorySource,
    WaybackRetailHistorySource,
)
from myne.services.pricing.service import MarketPriceService, PricingPolicy
from myne.services.pricing.sources import (
    EbayListingsSource,
    GoogleShoppingSource,
    PriceSource,
    SerperShoppingSource,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    appraisals: BagAppraisalService
    integrations: Mapping[str, bool]


ContainerFactory = Callable[[Settings], AbstractAsyncContextManager[Container]]


@asynccontextmanager
async def build_container(settings: Settings) -> AsyncIterator[Container]:
    async with AsyncExitStack() as stack:
        raw_http = await stack.enter_async_context(
            httpx.AsyncClient(
                timeout=httpx.Timeout(settings.http_timeout_seconds, connect=10.0),
                limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
                follow_redirects=True,
                headers={"User-Agent": f"MYNE-AI/{__version__}"},
            )
        )
        http = HttpClient(raw_http, max_attempts=settings.http_max_attempts)

        llm = _build_llm(settings)
        stack.push_async_callback(llm.aclose)

        search_currency = currency_for_country(settings.search_country, settings.default_currency)
        search_options = {
            "country": settings.search_country,
            "language": settings.search_language,
            "default_currency": search_currency,
        }
        vision_key = secret_value(settings.google_vision_api_key)
        serpapi_key = secret_value(settings.serp_api_key)
        serper_key = secret_value(settings.serper_api_key)

        vision = GoogleVisionClient(http, vision_key) if vision_key else None
        serpapi = SerpApiClient(http, serpapi_key, **search_options) if serpapi_key else None
        serper = SerperClient(http, serper_key, **search_options) if serper_key else None

        identifier = BagIdentifier(
            llm=llm,
            preprocessor=ImagePreprocessor(max_upload_bytes=settings.max_image_bytes),
            policy=IdentificationPolicy(
                auto_confirm_confidence=settings.auto_confirm_confidence,
                auto_confirm_margin=settings.auto_confirm_margin,
            ),
            vision=vision,
            serpapi=serpapi,
            serper=serper,
        )
        prices = MarketPriceService(
            sources=_build_price_sources(settings, http, llm, serpapi, serper),
            fx=FrankfurterFx(http, rates_url=settings.fx_rates_url),
            policy=PricingPolicy(
                history_months=settings.price_history_months,
                cache_ttl_seconds=settings.price_cache_ttl_seconds,
                source_timeout_seconds=settings.price_source_timeout_seconds,
            ),
        )
        integrations = {
            "llm": True,
            "google_vision": vision is not None,
            "serpapi": serpapi is not None,
            "serper": serper is not None,
        }
        logger.info("Container ready", extra={"ctx": {"llm": llm.name, **integrations}})

        images = ImageFetcher(
            raw_http,
            max_bytes=settings.max_image_bytes,
            timeout_seconds=settings.image_fetch_timeout_seconds,
        )
        yield Container(
            settings=settings,
            appraisals=BagAppraisalService(
                images=images,
                identifier=identifier,
                prices=prices,
                currency=settings.default_currency,
            ),
            integrations=integrations,
        )


def _build_llm(settings: Settings) -> StructuredLLM:
    factories: dict[str, Callable[[], StructuredLLM]] = {}
    if key := secret_value(settings.openai_api_key):
        factories["openai"] = partial(
            OpenAILLM,
            api_key=key,
            model=settings.openai_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if key := secret_value(settings.gemini_api_key):
        factories["gemini"] = partial(
            GeminiLLM,
            api_key=key,
            model=settings.gemini_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if not factories:
        raise ConfigurationError("No LLM configured: set OPENAI_API_KEY or GEMINI_API_KEY.")

    primary_name = (
        settings.llm_provider if settings.llm_provider in factories else next(iter(factories))
    )
    primary = factories.pop(primary_name)()
    if settings.llm_fallback_enabled and factories:
        return FallbackLLM(primary, next(iter(factories.values()))())
    return primary


def _build_price_sources(
    settings: Settings,
    http: HttpClient,
    llm: StructuredLLM,
    serpapi: SerpApiClient | None,
    serper: SerperClient | None,
) -> list[PriceSource]:
    sources: list[PriceSource] = []
    if serpapi is not None:
        sources += [GoogleShoppingSource(serpapi), EbayListingsSource(serpapi)]
    if serper is not None:
        sources += [
            SerperShoppingSource(serper),
            ReportedPriceHistorySource(serper=serper, llm=llm),
            WaybackRetailHistorySource(
                serper=serper, wayback=WaybackClient(http), max_pages=settings.wayback_max_pages
            ),
        ]
    return sources
