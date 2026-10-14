from decimal import Decimal

import pytest
from pydantic import ValidationError

from myne.api.schemas import BagPriceRequest, ImagePriceRequest


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
