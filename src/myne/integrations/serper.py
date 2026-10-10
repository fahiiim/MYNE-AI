from typing import Any

from myne.core.errors import UpstreamServiceError
from myne.core.http import HttpClient
from myne.domain.money import parse_price
from myne.integrations.types import MarketListing, WebResult


class SerperClient:
    _BASE_URL = "https://google.serper.dev"
    _SERVICE = "serper"

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

    async def search(self, query: str, *, num: int = 10, tbs: str | None = None) -> list[WebResult]:
        payload = await self._post("search", {"q": query, "num": num, "tbs": tbs})
        return [self._web_result(item) for item in payload.get("organic", []) if item.get("link")]

    async def news(self, query: str, *, num: int = 10, tbs: str | None = None) -> list[WebResult]:
        payload = await self._post("news", {"q": query, "num": num, "tbs": tbs})
        return [self._web_result(item) for item in payload.get("news", []) if item.get("link")]

    async def shopping(self, query: str, *, num: int = 40) -> list[MarketListing]:
        payload = await self._post("shopping", {"q": query, "num": num})
        return [
            MarketListing(
                title=item["title"],
                url=item.get("link"),
                seller=item.get("source"),
                price=parse_price(item.get("price"), default_currency=self._currency),
                condition_hint=None,
            )
            for item in payload.get("shopping", [])
            if item.get("title")
        ]

    @staticmethod
    def _web_result(item: dict[str, Any]) -> WebResult:
        return WebResult(
            title=item.get("title", ""),
            url=item["link"],
            snippet=item.get("snippet", ""),
            date_text=item.get("date"),
            source=item.get("source"),
        )

    async def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = await self._http.request_json(
            self._SERVICE,
            "POST",
            f"{self._BASE_URL}/{endpoint}",
            json={
                **{k: v for k, v in body.items() if v is not None},
                "gl": self._country,
                "hl": self._language,
            },
            headers={"X-API-KEY": self._api_key},
        )
        if not isinstance(payload, dict):
            raise UpstreamServiceError(self._SERVICE, f"{endpoint}: malformed response")
        return payload
