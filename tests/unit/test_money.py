from decimal import Decimal

import pytest

from myne.domain.money import detect_currency, money_from, parse_amount, parse_price


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("1,234.56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),
        ("12,50", Decimal("12.50")),
        ("2.450", Decimal("2450")),
        ("10,400", Decimal("10400")),
        ("1,23,456", Decimal("123456")),
        ("2 450", Decimal("2450")),
        ("980", Decimal("980")),
    ],
)
def test_parse_amount_handles_locales(token: str, expected: Decimal) -> None:
    assert parse_amount(token) == expected


@pytest.mark.parametrize(
    ("raw", "currency", "amount"),
    [
        ("$12,100.00", "USD", Decimal("12100.00")),
        ("US $2,450", "USD", Decimal("2450")),
        ("€ 9.800", "EUR", Decimal("9800")),
        ("£7,250", "GBP", Decimal("7250")),
        ("HK$88,000", "HKD", Decimal("88000")),
        ("AED 45,000", "AED", Decimal("45000")),
        ("$24.60 - $91.01", "USD", Decimal("24.60")),
    ],
)
def test_parse_price(raw: str, currency: str, amount: Decimal) -> None:
    money = parse_price(raw)
    assert money is not None
    assert (money.currency, money.amount) == (currency, amount)


def test_parse_price_rejects_text_without_amount() -> None:
    assert parse_price("Price on request", default_currency="USD") is None


def test_detect_currency_prefers_specific_dollar_symbols() -> None:
    assert detect_currency("C$1,200") == "CAD"


def test_money_from_prefers_extracted_value_with_raw_currency() -> None:
    money = money_from("€1.234,00", 1234.0, default_currency="USD")
    assert money is not None
    assert (money.currency, money.amount) == ("EUR", Decimal("1234.0"))
