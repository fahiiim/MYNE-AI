import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from myne.container import Container
from myne.core.config import Settings
from myne.core.errors import ImageFetchError
from myne.domain.models import (
    BagAttributes,
    BagCandidate,
    BagIdentity,
    IdentificationResult,
    PriceReport,
)
from myne.main import create_app
from myne.services.appraisal import BagAppraisalService
from myne.services.contracts import IdentificationRequest
from myne.services.progress import IdentificationStage, ProgressCallback, emit

IDENTITY = BagIdentity(brand="Louis Vuitton", model="Neverfull", size="MM")
IMAGE_URL = "https://cdn.example.com/bag.jpg"


class StubImages:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def fetch(self, url: str) -> bytes:
        if self._fail:
            raise ImageFetchError("Image URL returned HTTP 404")
        return b"image-bytes"


class StubIdentifier:
    def __init__(self) -> None:
        self.requests: list[IdentificationRequest] = []

    async def identify(
        self, request: IdentificationRequest, *, progress: ProgressCallback | None = None
    ) -> IdentificationResult:
        self.requests.append(request)
        await emit(progress, IdentificationStage.ATTRIBUTES_EXTRACTED, {"attributes": {}})
        return IdentificationResult(
            image_sha256="abc",
            attributes=BagAttributes(
                is_handbag=True,
                brand="Louis Vuitton",
                model_family="Neverfull",
                size="MM",
                material="Monogram canvas",
                color="Brown",
                hardware=None,
                apparent_condition="good",
                distinctive_features=[],
                visible_text=[],
                confidence=0.9,
            ),
            candidates=[
                BagCandidate(identity=IDENTITY, confidence=0.93, rationale="ok", evidence=[])
            ],
            needs_confirmation=False,
            warnings=[],
        )


class StubPrices:
    def __init__(self) -> None:
        self.calls: list[tuple[BagIdentity, str | None]] = []

    async def report(
        self, identity: BagIdentity, *, currency: str, search_query: str | None = None
    ) -> PriceReport:
        self.calls.append((identity, search_query))
        return PriceReport(
            identity=identity,
            currency=currency,
            generated_at=datetime(2026, 10, 11, tzinfo=UTC),
            current=[],
            history=[],
            sources=[],
            warnings=[],
        )


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
                appraisals=BagAppraisalService(
                    images=self.images,
                    identifier=self.identifier,
                    prices=self.prices,
                    currency=app_settings.default_currency,
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


def test_identify_upload(client: TestClient, harness: Harness) -> None:
    response = client.post("/api/v1/identify/upload", params={"url": IMAGE_URL, "user_id": "u-42"})
    assert response.status_code == 200
    body = response.json()
    assert (body["user_id"], body["image_url"]) == ("u-42", IMAGE_URL)
    assert body["candidates"][0]["identity"]["model"] == "Neverfull"
    assert harness.identifier.requests[0].image_url == IMAGE_URL


def test_identify_upload_defaults_user_and_requires_url(client: TestClient) -> None:
    assert (
        client.post("/api/v1/identify/upload", params={"url": IMAGE_URL}).json()["user_id"]
        == "anonymous"
    )

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


def test_identify_stream_reports_errors_as_events(settings: Settings) -> None:
    with (
        Harness(images_fail=True).client(settings) as client,
        client.stream(
            "POST", "/api/v1/identify/upload/stream", params={"url": IMAGE_URL}
        ) as response,
    ):
        events = _sse_events(response.read().decode())

    assert events == [("error", events[0][1])]
    assert events[0][1]["type"] == "urn:myne:error:image_unreachable"


def test_price_by_image(client: TestClient, harness: Harness) -> None:
    response = client.post(
        "/api/v1/bags/price/by-image",
        json={"image_url": IMAGE_URL, "image_search_query": "LV Neverfull", "purchase_price": 1500},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bag"]["model"] == "Neverfull"
    assert body["valuation"]["condition"] == "good"
    assert body["valuation"]["purchase_price"] == 1500.0
    assert harness.identifier.requests[0].lens_query == "LV Neverfull"


def test_price_bag(client: TestClient, harness: Harness) -> None:
    response = client.post(
        "/api/v1/bags/price",
        json={
            "brand": "Louis Vuitton",
            "model": "Neverfull",
            "condition": "Excellent",
            "color": ["Brown"],
            "size": "MM",
            "image_search_query": "louis vuitton neverfull mm monogram",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valuation"]["condition"] == "excellent"
    assert body["valuation"]["basis"] == "none"
    identity, search_query = harness.prices.calls[0]
    assert identity.variant is None
    assert search_query == "louis vuitton neverfull mm monogram"


def test_price_bag_validation_error(client: TestClient) -> None:
    response = client.post("/api/v1/bags/price", json={"brand": "Chanel"})
    assert response.status_code == 422
    assert response.json()["type"] == "urn:myne:error:validation_error"
