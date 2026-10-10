from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from myne.container import Container
from myne.core.config import Settings
from myne.domain.models import (
    BagAttributes,
    BagCandidate,
    BagIdentity,
    IdentificationResult,
    PriceReport,
)
from myne.main import create_app
from myne.services.appraisal import AppraisalService

IDENTITY = BagIdentity(brand="Louis Vuitton", model="Neverfull", size="MM")


class StubIdentifier:
    def __init__(self, *, confident: bool) -> None:
        self._confident = confident

    async def identify(self, image: bytes, *, notes: str | None = None) -> IdentificationResult:
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
                distinctive_features=[],
                visible_text=[],
                confidence=0.9,
            ),
            candidates=[
                BagCandidate(identity=IDENTITY, confidence=0.93, rationale="ok", evidence=[])
            ],
            needs_confirmation=not self._confident,
            warnings=[],
        )


class StubPrices:
    async def report(self, identity: BagIdentity, *, currency: str) -> PriceReport:
        return PriceReport(
            identity=identity,
            currency=currency,
            generated_at=datetime(2026, 10, 10, tzinfo=UTC),
            current=[],
            history=[],
            sources=[],
            warnings=[],
        )


def _client(settings: Settings, *, confident: bool = True) -> TestClient:
    @asynccontextmanager
    async def factory(app_settings: Settings) -> AsyncIterator[Container]:
        identifier, prices = StubIdentifier(confident=confident), StubPrices()
        yield Container(
            settings=app_settings,
            identifier=identifier,
            prices=prices,
            appraisals=AppraisalService(identifier=identifier, prices=prices),
            integrations={"llm": True},
        )

    return TestClient(create_app(settings, container_factory=factory))


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with _client(settings) as test_client:
        yield test_client


def test_health_and_request_id(client: TestClient) -> None:
    response = client.get("/health/ready", headers={"x-request-id": "req-123"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    assert response.json()["integrations"] == {"llm": True}


def test_identification_accepts_image(client: TestClient, jpeg_bytes: bytes) -> None:
    response = client.post(
        "/v1/identifications",
        files={"image": ("bag.jpg", jpeg_bytes, "image/jpeg")},
        data={"notes": "gift from 2023"},
    )
    assert response.status_code == 200
    assert response.json()["candidates"][0]["identity"]["model"] == "Neverfull"


def test_identification_rejects_unsupported_media(client: TestClient) -> None:
    response = client.post(
        "/v1/identifications", files={"image": ("bag.gif", b"GIF89a", "image/gif")}
    )
    assert response.status_code == 415
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:myne:error:unsupported_media_type"


def test_price_report_validates_and_uppercases_currency(client: TestClient) -> None:
    response = client.post(
        "/v1/price-reports", json={"identity": IDENTITY.model_dump(), "currency": "eur"}
    )
    assert response.status_code == 200
    assert response.json()["currency"] == "EUR"

    invalid = client.post("/v1/price-reports", json={"identity": {"brand": ""}})
    assert invalid.status_code == 422
    assert invalid.json()["type"] == "urn:myne:error:validation_error"


def test_appraisal_skips_pricing_when_confirmation_needed(
    settings: Settings, jpeg_bytes: bytes
) -> None:
    with _client(settings, confident=False) as client:
        response = client.post(
            "/v1/appraisals", files={"image": ("bag.jpg", jpeg_bytes, "image/jpeg")}
        )
    assert response.status_code == 200
    assert response.json()["prices"] is None


def test_appraisal_prices_confident_identification(client: TestClient, jpeg_bytes: bytes) -> None:
    response = client.post(
        "/v1/appraisals",
        files={"image": ("bag.jpg", jpeg_bytes, "image/jpeg")},
        data={"currency": "usd"},
    )
    assert response.status_code == 200
    assert response.json()["prices"]["currency"] == "USD"
