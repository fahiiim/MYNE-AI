"""OpenAPI examples shown as pre-filled dropdowns in Swagger UI (/docs)."""

from typing import Any

_OSTRICH_BIRKIN = (
    "https://upload.wikimedia.org/wikipedia/commons/6/6b/Hermes_Ostrich_Birkin_Bag.jpg"
)
_CHANEL_FLAP = (
    "https://upload.wikimedia.org/wikipedia/commons/1/19/Chanel_CLASSIC_Double_Flap_2.55_.jpg"
)

ANALYZE_EXAMPLES: dict[str, Any] = {
    "image_only": {
        "summary": "Image link only (identified via Google Lens)",
        "value": {"image_url": _CHANEL_FLAP, "user_id": "user_123"},
    },
    "image_with_details": {
        "summary": "Image link plus details and purchase price",
        "value": {
            "image_url": _OSTRICH_BIRKIN,
            "user_id": "user_123",
            "brand": "Hermès",
            "condition": "Excellent",
            "size": "30",
            "purchase_price": 18000,
            "image_search_query": "Hermes Birkin 30 ostrich",
        },
    },
    "details_only": {
        "summary": "Details only, no image",
        "value": {
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
        },
    },
    "camel_case_nested": {
        "summary": "camelCase and nested JSON from a backend",
        "value": {
            "userId": "user_123",
            "imageUrl": _CHANEL_FLAP,
            "bag": {
                "brandName": "Chanel",
                "modelName": "Classic Double Flap",
                "colour": "Black, Gold",
                "condition": "Very Good",
            },
            "pricePaid": "$6,800",
        },
    },
    "unknown_fields": {
        "summary": "Unknown fields are kept and passed to the AI as context",
        "value": {
            "photos": [{"src": _OSTRICH_BIRKIN}],
            "listing_title": "Authentic Hermes Birkin 30 Ostrich, receipt included",
            "seller_rating": 4.9,
        },
    },
    "invalid": {
        "summary": "Invalid: no image and no brand/model (expect 422)",
        "value": {"condition": "Good", "color": "Black"},
    },
}
