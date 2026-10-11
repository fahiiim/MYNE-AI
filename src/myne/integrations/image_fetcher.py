import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import httpx

from myne.core.errors import (
    ImageFetchError,
    InvalidImageUrlError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)

Resolver = Callable[[str, int], Awaitable[list[str]]]

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_GENERIC_CONTENT_TYPES = frozenset({"", "application/octet-stream", "binary/octet-stream"})


async def _system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class ImageFetcher:
    """Downloads user-supplied image URLs with SSRF protection.

    Every hop (including redirects) must resolve exclusively to public addresses.
    Resolution and connection are separate steps, so DNS rebinding is mitigated,
    not eliminated; run the service without access to sensitive internal networks.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_bytes: int,
        max_redirects: int = 3,
        timeout_seconds: float = 15.0,
        resolver: Resolver = _system_resolver,
    ) -> None:
        self._client = client
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._timeout = timeout_seconds
        self._resolver = resolver

    async def fetch(self, url: str) -> bytes:
        current = url
        for _ in range(self._max_redirects + 1):
            await self._assert_public(current)
            try:
                async with self._client.stream(
                    "GET", current, follow_redirects=False, timeout=self._timeout
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ImageFetchError("Redirect without a Location header")
                        current = urljoin(current, location)
                        continue
                    return await self._read_image(response)
            except httpx.HTTPError as exc:
                raise ImageFetchError(f"Download failed ({type(exc).__name__})") from None
        raise ImageFetchError("Too many redirects")

    async def _read_image(self, response: httpx.Response) -> bytes:
        if response.status_code != 200:
            raise ImageFetchError(f"Image URL returned HTTP {response.status_code}")

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if not content_type.startswith("image/") and content_type not in _GENERIC_CONTENT_TYPES:
            raise UnsupportedMediaTypeError(f"URL does not point to an image ({content_type})")

        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self._max_bytes:
            raise PayloadTooLargeError(f"Image exceeds {self._max_bytes} bytes")

        buffer = bytearray()
        async for chunk in response.aiter_bytes():
            buffer.extend(chunk)
            if len(buffer) > self._max_bytes:
                raise PayloadTooLargeError(f"Image exceeds {self._max_bytes} bytes")
        if not buffer:
            raise ImageFetchError("Image URL returned an empty body")
        return bytes(buffer)

    async def _assert_public(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme.lower() not in _ALLOWED_SCHEMES or not parts.hostname:
            raise InvalidImageUrlError("Only absolute http(s) URLs are supported")
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)

        try:
            addresses = await self._resolver(parts.hostname, port)
        except OSError:
            raise ImageFetchError("Image host could not be resolved") from None
        if not addresses:
            raise ImageFetchError("Image host could not be resolved")
        for address in addresses:
            if not ipaddress.ip_address(address.split("%")[0]).is_global:
                raise InvalidImageUrlError("Image URL resolves to a non-public address")
