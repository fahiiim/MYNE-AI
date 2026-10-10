from typing import Any

from myne.core.errors import UpstreamServiceError
from myne.core.http import HttpClient
from myne.domain.models import Money
from myne.domain.money import money_from
from myne.integrations.types import LensMatch, MarketListing


class SerpApiClient:
    """SerpApi engines used by MYNE: image upload + Google Lens, Google Shopping, eBay."""

    _BASE_URL = "https://serpapi.com"
    _SERVICE = "serpapi"
    _NO_RESULTS_MARKER = "hasn't returned any results"

    def __init__(
        self,
        http: HttpClient,
        api_key: str,
        *,
        country: str,
        language: str,
        default_currency: str,
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._country = country
        self._language = language
        self._currency = default_currency

    async def upload_image(self, data: bytes, mime_type: str) -> str:
        """Returns an `image_id` valid for ~10 minutes. SerpApi caps uploads at 500 KB."""
        payload = await self._http.request_json(
            self._SERVICE,
            "POST",
            f"{self._BASE_URL}/image",
            data={"api_key": self._api_key},
            files={"image": ("bag.jpg", data, mime_type)},
        )
        if not isinstance(payload, dict) or payload.get("error"):
            error = payload.get("error") if isinstance(payload, dict) else "malformed response"
            raise UpstreamServiceError(self._SERVICE, f"image upload failed: {error}")
        image_id = payload.get("image_id")
        if not isinstance(image_id, str) or not image_id:
            raise UpstreamServiceError(self._SERVICE, "image upload returned no image_id")
        return image_id

    async def google_lens(self, *, image_id: str, search_type: str = "all") -> list[LensMatch]:
        payload = await self._search(
            "google_lens",
            {
                "image_id": image_id,
                "type": search_type,
                "hl": self._language,
                "country": self._country,
            },
        )
        return [
            LensMatch(
                title=item["title"],
                url=item.get("link"),
                source=item.get("source"),
                thumbnail_url=item.get("thumbnail"),
                price=self._lens_price(item.get("price")),
            )
            for item in payload.get("visual_matches", [])
            if item.get("title")
        ]

    async def google_shopping(self, query: str) -> list[MarketListing]:
        payload = await self._search(
            "google_shopping", {"q": query, "gl": self._country, "hl": self._language}
        )
        return [
            MarketListing(
                title=item["title"],
                url=item.get("product_link") or item.get("link"),
                seller=item.get("source"),
                price=money_from(
                    item.get("price"), item.get("extracted_price"), default_currency=self._currency
                ),
                condition_hint=item.get("second_hand_condition"),
            )
            for item in payload.get("shopping_results", [])
            if item.get("title")
        ]

    async def ebay(self, query: str, *, page_size: int = 50) -> list[MarketListing]:
        payload = await self._search("ebay", {"_nkw": query, "_ipg": page_size})
        listings: list[MarketListing] = []
        for item in payload.get("organic_results", []):
            if not item.get("title"):
                continue
            price: dict[str, Any] = item.get("price") or {}
            price = price.get("from", price)
            seller = item.get("seller") or {}
            listings.append(
                MarketListing(
                    title=item["title"],
                    url=item.get("link"),
                    seller=f"eBay - {seller['username']}" if seller.get("username") else "eBay",
                    price=money_from(
                        price.get("raw"), price.get("extracted"), default_currency=self._currency
                    ),
                    condition_hint=item.get("condition"),
                )
            )
        return listings

    def _lens_price(self, price: dict[str, Any] | None) -> Money | None:
        if not price:
            return None
        return money_from(
            price.get("value"), price.get("extracted_value"), default_currency=self._currency
        )

    async def _search(self, engine: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self._http.request_json(
            self._SERVICE,
            "GET",
            f"{self._BASE_URL}/search.json",
            params={**params, "engine": engine, "api_key": self._api_key},
        )
        if not isinstance(payload, dict):
            raise UpstreamServiceError(self._SERVICE, f"{engine}: malformed response")
        error = payload.get("error")
        if error and self._NO_RESULTS_MARKER not in str(error):
            raise UpstreamServiceError(self._SERVICE, f"{engine}: {error}")
        return payload
