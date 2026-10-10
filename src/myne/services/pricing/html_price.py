"""Extract a product's list price from e-commerce HTML via JSON-LD and meta tags."""

import json
import re
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Any

from myne.domain.models import Money
from myne.domain.money import parse_amount

_LD_JSON = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I
)
_META_TAG = re.compile(r"<meta\s[^>]*>", re.I)
_ATTRIBUTE = re.compile(r"([\w:-]+)\s*=\s*[\"']([^\"']*)[\"']")
_PRICE_KEYS = ("product:price:amount", "og:price:amount")
_CURRENCY_KEYS = ("product:price:currency", "og:price:currency")


def extract_product_price(html: str) -> Money | None:
    return _from_json_ld(html) or _from_meta(html)


def _from_json_ld(html: str) -> Money | None:
    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            if _is_product(node) and (money := _offer_price(node.get("offers"))):
                return money
    return None


def _walk(data: Any) -> Iterator[dict[str, Any]]:
    if isinstance(data, list):
        for item in data:
            yield from _walk(item)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in data:
                yield from _walk(data[key])


def _is_product(node: dict[str, Any]) -> bool:
    node_type = node.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    return any(t in {"Product", "ProductGroup"} for t in types)


def _offer_price(offers: Any) -> Money | None:
    for offer in offers if isinstance(offers, list) else [offers]:
        if not isinstance(offer, dict):
            continue
        spec = offer.get("priceSpecification")
        spec = spec[0] if isinstance(spec, list) and spec else spec
        candidates = (
            offer.get("price"),
            offer.get("lowPrice"),
            spec.get("price") if isinstance(spec, dict) else None,
        )
        currency = offer.get("priceCurrency") or (
            spec.get("priceCurrency") if isinstance(spec, dict) else None
        )
        for value in candidates:
            if (amount := _to_decimal(value)) and isinstance(currency, str):
                return _money(amount, currency)
    return None


def _from_meta(html: str) -> Money | None:
    values: dict[str, str] = {}
    for tag in _META_TAG.findall(html):
        attrs = {k.lower(): v for k, v in _ATTRIBUTE.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if key and "content" in attrs:
            values.setdefault(key, attrs["content"])

    amount = next((_to_decimal(values[k]) for k in _PRICE_KEYS if k in values), None)
    currency = next((values[k] for k in _CURRENCY_KEYS if k in values), None)
    if amount and currency:
        return _money(amount, currency)
    return None


def _to_decimal(value: Any) -> Decimal | None:
    amount: Decimal | None = None
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            amount = Decimal(str(value))
        except InvalidOperation:
            return None
    elif isinstance(value, str):
        amount = parse_amount(value)
    return amount if amount is not None and amount > 0 else None


def _money(amount: Decimal, currency: str) -> Money | None:
    code = currency.strip().upper()
    return Money(amount=amount, currency=code) if re.fullmatch(r"[A-Z]{3}", code) else None
