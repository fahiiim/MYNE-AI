"""OpenAPI examples shown as pre-filled dropdowns in Swagger UI (/docs)."""

from typing import Any

_OSTRICH_BIRKIN = (
    "https://upload.wikimedia.org/wikipedia/commons/6/6b/Hermes_Ostrich_Birkin_Bag.jpg"
)
_CROC_BIRKIN = "https://upload.wikimedia.org/wikipedia/commons/2/2e/Croc_Birkin_bag.jpg"
_CHANEL_FLAP = (
    "https://upload.wikimedia.org/wikipedia/commons/1/19/Chanel_CLASSIC_Double_Flap_2.55_.jpg"
)

IMAGE_URL_EXAMPLES: dict[str, Any] = {
    "hermes_ostrich_birkin": {"summary": "Hermès Birkin (ostrich)", "value": _OSTRICH_BIRKIN},
    "chanel_classic_flap": {"summary": "Chanel Classic Double Flap", "value": _CHANEL_FLAP},
    "hermes_croc_birkin": {"summary": "Hermès Birkin (crocodile)", "value": _CROC_BIRKIN},
}

USER_ID_EXAMPLES: dict[str, Any] = {
    "anonymous": {"summary": "Anonymous", "value": "anonymous"},
    "user": {"summary": "Signed-in user", "value": "user_123"},
}

PRICE_BY_IMAGE_EXAMPLES: dict[str, Any] = {
    "with_hint_and_purchase_price": {
        "summary": "Birkin with search hint and purchase price",
        "value": {
            "image_url": _OSTRICH_BIRKIN,
            "image_search_query": "Hermes Birkin 30 ostrich",
            "purchase_price": 18000,
        },
    },
    "image_only": {
        "summary": "Image URL only",
        "value": {"image_url": _CHANEL_FLAP},
    },
}

BAG_PRICE_EXAMPLES: dict[str, Any] = {
    "full_payload": {
        "summary": "Hermès Birkin 30 Togo (all fields)",
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
            "image_search_query": "Hermes Birkin 30 Togo Gold",
        },
    },
    "minimal_string_color": {
        "summary": "Chanel Classic Flap (required fields, color as string)",
        "value": {
            "brand": "Chanel",
            "model": "Classic Double Flap",
            "condition": "Very Good",
            "color": "Black",
            "size": "Medium",
        },
    },
    "special_variant": {
        "summary": "Hermès Birkin 25 Himalaya (special variant)",
        "value": {
            "brand": "Hermès",
            "model": "Birkin",
            "condition": "New",
            "size": "25",
            "leather": "Niloticus crocodile",
            "special_variant": "Himalaya",
        },
    },
    "louis_vuitton": {
        "summary": "Louis Vuitton Neverfull MM",
        "value": {
            "brand": "Louis Vuitton",
            "model": "Neverfull",
            "condition": "Good",
            "color": ["Brown"],
            "leather": "Monogram canvas",
            "size": "MM",
            "purchase_price": 1800,
        },
    },
    "invalid_missing_condition": {
        "summary": "Invalid: missing condition (expect 422)",
        "value": {"brand": "Chanel", "model": "Boy"},
    },
}
