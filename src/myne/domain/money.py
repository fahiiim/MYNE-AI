import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from myne.domain.models import Money

_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("US$", "USD"),
    ("CA$", "CAD"),
    ("C$", "CAD"),
    ("AU$", "AUD"),
    ("A$", "AUD"),
    ("HK$", "HKD"),
    ("S$", "SGD"),
    ("NZ$", "NZD"),
    ("R$", "BRL"),
    ("€", "EUR"),
    ("£", "GBP"),
    ("¥", "JPY"),
    ("₹", "INR"),
    ("₩", "KRW"),
    ("৳", "BDT"),
    ("$", "USD"),
)

_ISO_CODES = frozenset(
    {
        "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "HKD", "SGD", "NZD", "AED",
        "SAR", "QAR", "INR", "BDT", "KRW", "SEK", "NOK", "DKK", "PLN", "CZK", "TRY", "MYR",
        "THB", "BRL", "MXN",
    }
)  # fmt: skip

_COUNTRY_CURRENCY = {
    "us": "USD", "gb": "GBP", "uk": "GBP", "ca": "CAD", "au": "AUD", "jp": "JPY", "in": "INR",
    "bd": "BDT", "ae": "AED", "sg": "SGD", "hk": "HKD", "ch": "CHF", "de": "EUR", "fr": "EUR",
    "it": "EUR", "es": "EUR", "nl": "EUR",
}  # fmt: skip

_ISO_PATTERN = re.compile(r"\b([A-Z]{3})\b")
_AMOUNT_PATTERN = re.compile(r"\d[\d\s\u00a0.,']*")
_CENT = Decimal("0.01")


def currency_for_country(country: str, fallback: str = "USD") -> str:
    return _COUNTRY_CURRENCY.get(country.lower(), fallback)


def detect_currency(raw: str) -> str | None:
    for match in _ISO_PATTERN.finditer(raw.upper()):
        if match.group(1) in _ISO_CODES:
            return match.group(1)
    for symbol, code in _SYMBOLS:
        if symbol in raw:
            return code
    return None


def parse_amount(token: str) -> Decimal | None:
    """Parse '1,234.56', '1.234,56', '2 450' and '12,50' without knowing the locale.

    A lone separator followed by exactly three digits is treated as a thousands
    separator; handbag prices practically never carry three decimals.
    """
    cleaned = re.sub(r"[\s\u00a0']", "", token).strip(".,")
    if not cleaned:
        return None

    last_comma, last_dot = cleaned.rfind(","), cleaned.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        decimal_sep, thousands_sep = (",", ".") if last_comma > last_dot else (".", ",")
        cleaned = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif last_comma >= 0 or last_dot >= 0:
        sep = "," if last_comma >= 0 else "."
        tail = cleaned.rpartition(sep)[2]
        is_thousands = len(tail) == 3 or cleaned.count(sep) > 1
        cleaned = cleaned.replace(sep, "") if is_thousands else cleaned.replace(sep, ".")

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_price(raw: str | None, *, default_currency: str | None = None) -> Money | None:
    if not raw:
        return None
    currency = detect_currency(raw) or default_currency
    match = _AMOUNT_PATTERN.search(raw)
    if currency is None or match is None:
        return None
    amount = parse_amount(match.group())
    if amount is None or amount <= 0:
        return None
    return Money(amount=amount, currency=currency)


def money_from(
    raw: str | None, extracted: float | int | None, *, default_currency: str
) -> Money | None:
    """Prefer a provider's pre-extracted numeric value, taking the currency from the raw string."""
    if isinstance(extracted, int | float) and extracted > 0:
        currency = (detect_currency(raw) if raw else None) or default_currency
        return Money(amount=Decimal(str(extracted)), currency=currency)
    return parse_price(raw, default_currency=default_currency)


def quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)
