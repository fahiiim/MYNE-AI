from decimal import Decimal

import pytest
from pydantic import ValidationError

from myne.api.schemas import BagPriceRequest, ImagePriceRequest
from myne.domain.models import BagCandidate


def test_bag_price_request_maps_backend_contract() -> None:
    analysis_input = BagPriceRequest.model_validate(
        {
            "brand": "Hermès",
            "model": "Kelly",
            "condition": "Very Good",
            "color": "Noir",
            "leather": "Epsom",
            "size": "28",
            "special_variant": "Standard",
            "purchase_price": 12000,
        }
    ).to_input()
    assert analysis_input.color == ["Noir"]
    assert analysis_input.leather == "Epsom"
    assert analysis_input.special_variant is None
    assert analysis_input.hardware is None
    assert analysis_input.search_query is None
    assert analysis_input.purchase_price == Decimal("12000")


def test_bag_price_request_accepts_color_list_and_special_variant() -> None:
    analysis_input = BagPriceRequest.model_validate(
        {
            "brand": "Hermès",
            "model": "Birkin",
            "condition": "New",
            "color": ["Gris", "Blanc"],
            "special_variant": "Himalaya",
        }
    ).to_input()
    assert analysis_input.color == ["Gris", "Blanc"]
    assert analysis_input.special_variant == "Himalaya"


def test_bag_price_request_requires_condition() -> None:
    with pytest.raises(ValidationError):
        BagPriceRequest.model_validate({"brand": "Chanel", "model": "Boy"})


def test_image_price_request_treats_empty_query_as_absent() -> None:
    analysis_input = ImagePriceRequest.model_validate(
        {"image_url": "https://cdn.example.com/bag.jpg", "image_search_query": ""}
    ).to_input()
    assert analysis_input.search_query is None
    assert analysis_input.purchase_price is None


def test_searched_product_exact_structure() -> None:
    payload = {
        "rank": 1,
        "brand": "Chanel",
        "brandId": "brand-id",
        "model": "Classic Flap",
        "modelId": "model-id",
        "thumbnailUrl": "https://example.com/bag.jpg",
        "confidence": 94,
        "estimatedValueEUR": 8500,
        "detectedSize": "Medium",
        "detectedColors": ["Black"],
        "detectedHardware": "Gold-tone",
        "detectedLeathers": "Lambskin",
        "detectedConstruction": "Quilted",
        "detectedYear": "2022",
        "condition": "Very Good",
        "special_variant": "Classic",
        "alternativeColors": ["Navy", "Red"],
        "imageSearchQuery": "Chanel Classic Flap Medium black lambskin gold hardware",
        "analysis": (
            "The image appears to show a Chanel Classic Flap bag with "
            "quilted black lambskin and gold-tone hardware."
        ),
    }
    candidate = BagCandidate.model_validate(payload)
    dumped = candidate.model_dump(by_alias=True, mode="json")
    for key, expected_value in payload.items():
        assert (
            dumped[key] == expected_value
        ), f"Mismatch on {key}: {dumped.get(key)} != {expected_value}"
