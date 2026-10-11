from collections.abc import Callable

import httpx
import pytest

from myne.core.errors import (
    ImageFetchError,
    InvalidImageUrlError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from myne.integrations.image_fetcher import ImageFetcher

PUBLIC_IP = "93.184.216.34"


def _resolver(mapping: dict[str, str]) -> Callable[[str, int], object]:
    async def resolve(host: str, port: int) -> list[str]:
        return [mapping.get(host, PUBLIC_IP)]

    return resolve


def _fetcher(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    hosts: dict[str, str] | None = None,
    max_bytes: int = 1024,
) -> ImageFetcher:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ImageFetcher(client, max_bytes=max_bytes, resolver=_resolver(hosts or {}))  # type: ignore[arg-type]


async def test_downloads_public_image() -> None:
    fetcher = _fetcher(
        lambda r: httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})
    )
    assert await fetcher.fetch("https://cdn.example.com/bag.jpg") == b"img"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
async def test_blocks_non_public_addresses(address: str) -> None:
    fetcher = _fetcher(lambda r: httpx.Response(200), hosts={"internal.example": address})
    with pytest.raises(InvalidImageUrlError):
        await fetcher.fetch("http://internal.example/meta")


async def test_blocks_redirect_into_private_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://metadata.internal/latest"})

    fetcher = _fetcher(handler, hosts={"metadata.internal": "169.254.169.254"})
    with pytest.raises(InvalidImageUrlError):
        await fetcher.fetch("https://cdn.example.com/bag.jpg")


async def test_rejects_non_http_scheme() -> None:
    fetcher = _fetcher(lambda r: httpx.Response(200))
    with pytest.raises(InvalidImageUrlError):
        await fetcher.fetch("file:///etc/passwd")


async def test_enforces_size_limit_while_streaming() -> None:
    fetcher = _fetcher(
        lambda r: httpx.Response(200, content=b"x" * 2048, headers={"content-type": "image/png"}),
        max_bytes=1024,
    )
    with pytest.raises(PayloadTooLargeError):
        await fetcher.fetch("https://cdn.example.com/huge.png")


async def test_rejects_html_pages() -> None:
    fetcher = _fetcher(
        lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    )
    with pytest.raises(UnsupportedMediaTypeError):
        await fetcher.fetch("https://shop.example.com/product")


async def test_surfaces_upstream_status() -> None:
    fetcher = _fetcher(lambda r: httpx.Response(404))
    with pytest.raises(ImageFetchError, match="404"):
        await fetcher.fetch("https://cdn.example.com/missing.jpg")
