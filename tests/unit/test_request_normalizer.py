from decimal import Decimal

import pytest

from myne.api.request_normalizer import normalize_request
from myne.core.errors import InvalidRequestError

IMAGE_URL = "https://cdn.example.com/bag.jpg"


def test_image_link_alone_is_enough() -> None:
    result = normalize_request({"url": IMAGE_URL})
    assert result.image_url == IMAGE_URL
    assert result.user_id == "anonymous"
    assert result.has_bag_details is False


def test_backend_contract_fields_map_directly() -> None:
    result = normalize_request(
        {
            "brand": "Hermès",
            "model": "Birkin",
            "condition": "Excellent",
            "color": ["Gold"],
            "leather": "Togo",
            "hardware": "Gold hardware",
            "size": "30",
            "construction": "Retourne",
            "special_variant": "Standard",
            "purchase_price": 15000,
            "image_search_query": "Hermes Birkin 30",
        }
    )
    assert (result.brand, result.model, result.leather) == ("Hermès", "Birkin", "Togo")
    assert result.color == ["Gold"]
    assert result.special_variant is None
    assert result.purchase_price == Decimal("15000")
    assert result.search_query == "Hermes Birkin 30"


def test_camel_case_nested_and_joined_keys() -> None:
    result = normalize_request(
        {
            "user": {"id": 42},
            "imageUrl": IMAGE_URL,
            "bag": {"brandName": "Chanel", "modelName": "Classic Flap", "colour": "Black, Gold"},
            "pricePaid": "€6.800,00",
        }
    )
    assert result.user_id == "42"
    assert (result.brand, result.model) == ("Chanel", "Classic Flap")
    assert result.color == ["Black", "Gold"]
    assert result.purchase_price == Decimal("6800.00")
    assert result.currency == "EUR"


def test_image_lists_and_objects_are_unwrapped() -> None:
    assert normalize_request({"photos": [{"src": IMAGE_URL}]}).image_url == IMAGE_URL
    assert normalize_request({"images": ["", IMAGE_URL]}).image_url == IMAGE_URL


def test_top_level_values_win_and_duplicates_go_to_extra() -> None:
    result = normalize_request(
        {"brand": "Chanel", "model": "Boy", "item": {"brand": "Gucci", "listing_id": "L-1"}}
    )
    assert result.brand == "Chanel"
    assert result.extra == {"item.brand": "Gucci", "item.listing_id": "L-1"}


def test_explicit_currency_beats_currency_inferred_from_price() -> None:
    result = normalize_request(
        {"brand": "Chanel", "model": "Boy", "price": "$5,000", "currency": "gbp"}
    )
    assert result.currency == "GBP"
    assert result.purchase_price == Decimal("5000")


def test_price_object_form() -> None:
    result = normalize_request(
        {"brand": "Chanel", "model": "Boy", "purchase_price": {"amount": "1200", "currency": "USD"}}
    )
    assert (result.purchase_price, result.currency) == (Decimal("1200"), "USD")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"brand": "Chanel"},
        {"condition": "Good", "color": "Black"},
        {"brand": "Chanel", "model": "Boy", "purchase_price": -5},
        {"brand": "Chanel", "model": "Boy", "currency": "dollars"},
        {"brand": "x" * 81, "model": "Boy"},
    ],
)
def test_invalid_requests(payload: dict[str, object]) -> None:
    with pytest.raises(InvalidRequestError):
        normalize_request(payload)
