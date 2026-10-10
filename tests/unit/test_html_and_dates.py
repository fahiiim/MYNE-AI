from datetime import date
from decimal import Decimal

import pytest

from myne.services.pricing.dates import parse_month, parse_published
from myne.services.pricing.html_price import extract_product_price

TODAY = date(2026, 10, 10)


def test_extracts_price_from_json_ld_graph() -> None:
    html = """
    <script type="application/ld+json">
      {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList"},
        {"@type": "Product", "name": "Lady Dior Medium",
         "offers": {"@type": "Offer", "price": "6500.00", "priceCurrency": "USD"}}
      ]}
    </script>
    """
    money = extract_product_price(html)
    assert money is not None
    assert (money.amount, money.currency) == (Decimal("6500.00"), "USD")


def test_extracts_price_from_meta_tags_in_any_attribute_order() -> None:
    html = (
        '<meta content="4,950" property="product:price:amount">'
        '<meta property="product:price:currency" content="eur">'
    )
    money = extract_product_price(html)
    assert money is not None
    assert (money.amount, money.currency) == (Decimal("4950"), "EUR")


def test_returns_none_without_structured_price() -> None:
    assert extract_product_price("<html><body>Price upon request</body></html>") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3 days ago", date(2026, 10, 7)),
        ("2 months ago", date(2026, 8, 10)),
        ("yesterday", date(2026, 10, 9)),
        ("Mar 5, 2026", date(2026, 3, 5)),
        ("5 hours ago", TODAY),
        ("not a date", None),
        (None, None),
    ],
)
def test_parse_published(text: str | None, expected: date | None) -> None:
    assert parse_published(text, today=TODAY) == expected


def test_parse_month() -> None:
    assert parse_month("2026-05") == date(2026, 5, 1)
    assert parse_month("2026-13") is None
