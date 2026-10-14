import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from myne.container import Container
from myne.core.config import Settings
from myne.main import create_app
from myne.services.analysis import BagAnalysisService
from tests.fakes import StubIdentifier, StubImages, StubPrices

ANALYZE = "/api/v1/bags/analyze"
IMAGE_URL = "https://cdn.example.com/bag.jpg"


class Harness:
    def __init__(self, *, images_fail: bool = False) -> None:
        self.identifier = StubIdentifier()
        self.prices = StubPrices()
        self.images = StubImages(fail=images_fail)

    def client(self, settings: Settings) -> TestClient:
        @asynccontextmanager
        async def factory(app_settings: Settings) -> AsyncIterator[Container]:
            yield Container(
                settings=app_settings,
                analysis=BagAnalysisService(
                    images=self.images,
                    identifier=self.identifier,
                    prices=self.prices,
                    default_currency=app_settings.default_currency,
                ),
                integrations={"llm": True},
            )

        return TestClient(create_app(settings, container_factory=factory))


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(harness: Harness, settings: Settings) -> Iterator[TestClient]:
    with harness.client(settings) as test_client:
        yield test_client


def _sse_events(body: str) -> list[tuple[str, Any]]:
    events = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if not line.startswith(":"))
        if lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health_and_request_id(client: TestClient) -> None:
    response = client.get("/health/ready", headers={"x-request-id": "req-123"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"


def test_image_link_returns_identification_prices_and_history(
    client: TestClient, harness: Harness
) -> None:
    response = client.post(ANALYZE, json={"image_url": IMAGE_URL, "user_id": "u-42"})

    assert response.status_code == 200
    body = response.json()
    assert (body["mode"], body["user_id"], body["currency"]) == ("image", "u-42", "USD")
    assert body["bag"]["model"] == "Neverfull"
    assert body["identification"]["candidates"][0]["identity"]["brand"] == "Louis Vuitton"
    assert body["valuation"]["condition"] == "good"
    assert {"market_prices", "price_history", "sources", "warnings"} <= body.keys()
    assert harness.images.urls == [IMAGE_URL]


def test_flexible_backend_payload(client: TestClient, harness: Harness) -> None:
    response = client.post(
        ANALYZE,
        json={
            "userId": "u-7",
            "photo": {"url": IMAGE_URL},
            "bag": {"brandName": "Louis Vuitton", "colour": "Brown"},
            "pricePaid": "$1,500",
            "listing_title": "Neverfull MM",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "image_with_details"
    assert body["input"]["extra"] == {"listing_title": "Neverfull MM"}
    assert body["valuation"]["purchase_price"] == 1500.0
    assert body["bag"]["color"] == "Brown"


def test_query_params_are_merged_but_body_wins(client: TestClient, harness: Harness) -> None:
    response = client.post(
        ANALYZE,
        params={"url": IMAGE_URL, "user_id": "from-query"},
        json={"user_id": "from-body"},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "from-body"
    assert harness.images.urls == [IMAGE_URL]


def test_details_only(client: TestClient, harness: Harness) -> None:
    response = client.post(
        ANALYZE,
        json={"brand": "Hermès", "model": "Birkin", "condition": "Excellent", "size": "30"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["mode"], body["identification"]) == ("details", None)
    assert body["valuation"]["condition"] == "excellent"
    assert harness.identifier.requests == []


@pytest.mark.parametrize("payload", [None, {}, {"brand": "Chanel"}, {"color": "Black"}])
def test_invalid_requests_return_problem_json(client: TestClient, payload: Any) -> None:
    response = client.post(ANALYZE, json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:myne:error:invalid_request"


def test_stream_emits_stages_then_result(client: TestClient) -> None:
    with client.stream(
        "POST", ANALYZE, params={"stream": "true"}, json={"image_url": IMAGE_URL}
    ) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(response.read().decode())

    assert [name for name, _ in events] == ["stage"] * 4 + ["result"]
    assert [data["stage"] for _, data in events[:4]] == [
        "image_fetched",
        "attributes_extracted",
        "pricing_started",
        "pricing_completed",
    ]
    assert events[-1][1]["bag"]["model"] == "Neverfull"


def test_stream_validates_before_streaming(client: TestClient) -> None:
    response = client.post(ANALYZE, params={"stream": "true"}, json={"brand": "Chanel"})
    assert response.status_code == 422


def test_identify_upload(client: TestClient, harness: Harness) -> None:
    response = client.post("/api/v1/identify/upload", params={"url": IMAGE_URL, "user_id": "u-42"})
    assert response.status_code == 200
    body = response.json()
    assert (body["user_id"], body["image_url"]) == ("u-42", IMAGE_URL)
    assert body["candidates"][0]["identity"]["model"] == "Neverfull"
    assert harness.prices.calls == []


def test_identify_upload_defaults_user_and_requires_url(client: TestClient) -> None:
    body = client.post("/api/v1/identify/upload", params={"url": IMAGE_URL}).json()
    assert body["user_id"] == "anonymous"

    missing = client.post("/api/v1/identify/upload")
    assert missing.status_code == 422
    assert missing.headers["content-type"].startswith("application/problem+json")


def test_identify_stream_emits_stages_then_result(client: TestClient) -> None:
    with client.stream(
        "POST", "/api/v1/identify/upload/stream", params={"url": IMAGE_URL}
    ) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(response.read().decode())

    assert [name for name, _ in events] == ["stage", "stage", "result"]
    assert [data["stage"] for _, data in events[:2]] == ["image_fetched", "attributes_extracted"]
    assert events[-1][1]["user_id"] == "anonymous"


def test_price_by_image(client: TestClient, harness: Harness) -> None:
    response = client.post(
        "/api/v1/bags/price/by-image",
        json={"image_url": IMAGE_URL, "image_search_query": "LV Neverfull", "purchase_price": 1500},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "image"
    assert body["bag"]["model"] == "Neverfull"
    assert body["valuation"]["purchase_price"] == 1500.0
    assert harness.identifier.requests[0].lens_query == "LV Neverfull"
    assert harness.prices.calls[0]["search_query"] == "LV Neverfull"


def test_price_bag(client: TestClient, harness: Harness) -> None:
    response = client.post(
        "/api/v1/bags/price",
        json={
            "brand": "Louis Vuitton",
            "model": "Neverfull",
            "condition": "Excellent",
            "color": "Brown",
            "size": "MM",
            "special_variant": "Standard",
            "image_search_query": "louis vuitton neverfull mm monogram",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["mode"], body["identification"]) == ("details", None)
    assert body["valuation"]["condition"] == "excellent"
    assert body["bag"]["color"] == "Brown"
    assert body["bag"]["variant"] is None
    assert harness.prices.calls[0]["search_query"] == "louis vuitton neverfull mm monogram"
    assert harness.identifier.requests == []


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/bags/price", {"brand": "Chanel", "model": "Boy"}),
        ("/api/v1/bags/price/by-image", {"image_search_query": "Chanel"}),
        ("/api/v1/bags/price/by-image", {"image_url": "not a url"}),
    ],
)
def test_contract_validation_errors(client: TestClient, path: str, payload: Any) -> None:
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert response.json()["type"] == "urn:myne:error:validation_error"


def test_stream_reports_errors_as_events(settings: Settings) -> None:
    with (
        Harness(images_fail=True).client(settings) as client,
        client.stream(
            "POST", ANALYZE, params={"stream": "true"}, json={"image_url": IMAGE_URL}
        ) as response,
    ):
        events = _sse_events(response.read().decode())

    assert events == [("error", events[0][1])]
    assert events[0][1]["type"] == "urn:myne:error:image_unreachable"
