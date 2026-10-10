from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from myne.core.errors import UpstreamServiceError

_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class _RetryableResponseError(Exception):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"HTTP {response.status_code}")
        self.response = response


class HttpClient:
    """Outbound HTTP with bounded, jittered retries.

    Errors are re-raised `from None` and never include the URL, because several
    providers (SerpApi, Google Vision) authenticate through the query string.
    """

    def __init__(self, client: httpx.AsyncClient, *, max_attempts: int = 3) -> None:
        self._client = client
        self._max_attempts = max_attempts

    async def request(self, service: str, method: str, url: str, **kwargs: Any) -> httpx.Response:
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential_jitter(initial=0.5, max=8),
            retry=retry_if_exception_type((_RetryableResponseError, httpx.TransportError)),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    response = await self._client.request(method, url, **kwargs)
                    if response.status_code in _RETRYABLE_STATUS:
                        raise _RetryableResponseError(response)
        except _RetryableResponseError as exc:
            status = exc.response.status_code
            raise UpstreamServiceError(service, f"HTTP {status}", status=status) from None
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(service, type(exc).__name__) from None

        if response.is_error:
            status = response.status_code
            raise UpstreamServiceError(service, f"HTTP {status}", status=status)
        return response

    async def request_json(self, service: str, method: str, url: str, **kwargs: Any) -> Any:
        response = await self.request(service, method, url, **kwargs)
        try:
            return response.json()
        except ValueError:
            raise UpstreamServiceError(service, "response was not valid JSON") from None
