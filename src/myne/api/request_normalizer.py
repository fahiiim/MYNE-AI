"""Turns arbitrary caller JSON into an `AnalysisInput`.

Keys are matched against an alias table after canonicalization (case, `_`, `-`
and spaces are ignored), so `image_url`, `imageUrl` and `Image-URL` are the same
field. Nested objects are searched breadth-first, so top-level values win over
nested ones; `{"user": {"id": ...}}` also matches via the joined key `userid`.
Anything unrecognized is preserved in `extra` under its original dotted path.
"""

import re
from collections import deque
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from myne.core.errors import InvalidRequestError
from myne.domain.models import AnalysisInput
from myne.domain.money import detect_currency, parse_amount

_ALIASES: dict[str, tuple[str, ...]] = {
    "image_url": (
        "imageurl", "url", "image", "imagelink", "imageuri", "images", "imageurls",
        "photo", "photourl", "photos", "picture", "pictureurl", "pictures", "img", "imgurl",
    ),
    "user_id": ("userid", "user", "uid", "customerid", "accountid"),
    "brand": ("brand", "brandname", "designer", "maker", "manufacturer"),
    "model": ("model", "modelname", "bagmodel", "bagname", "style", "stylename"),
    "condition": ("condition", "bagcondition", "conditiongrade", "grade"),
    "size": ("size", "bagsize"),
    "leather": ("leather", "leathertype", "material", "materials"),
    "color": ("color", "colour", "colors", "colours"),
    "hardware": ("hardware", "hardwarecolor", "hardwarecolour"),
    "construction": ("construction", "stitching"),
    "special_variant": ("specialvariant", "variant", "edition", "specialedition"),
    "purchase_price": (
        "purchaseprice", "price", "pricepaid", "paidprice", "purchasecost", "cost", "boughtfor",
    ),
    "currency": ("currency", "currencycode", "purchasecurrency"),
    "search_query": ("imagesearchquery", "searchquery", "query", "q", "keywords"),
    "notes": ("notes", "note", "description", "details", "comments", "remarks"),
}  # fmt: skip

_FIELD_BY_ALIAS = {alias: name for name, aliases in _ALIASES.items() for alias in aliases}

_TEXT_LIMITS = {
    "user_id": 128,
    "brand": 80,
    "model": 120,
    "condition": 60,
    "size": 40,
    "leather": 120,
    "hardware": 120,
    "construction": 120,
    "special_variant": 120,
    "search_query": 300,
    "notes": 2000,
}
_COLOR_LIMIT = 40
_MAX_COLORS = 8
_MAX_EXTRA_FIELDS = 50
_STANDARD_VARIANTS = frozenset({"standard", "none", "regular", "na"})
_URL_KEYS = ("url", "src", "href", "link", "uri")
_PRICE_AMOUNT_KEYS = ("amount", "value", "price")
_AMOUNT = re.compile(r"-?\d[\d\s.,']*")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def canonical_key(key: str) -> str:
    return _NON_ALNUM.sub("", key.lower())


def normalize_request(payload: Mapping[str, Any]) -> AnalysisInput:
    builder = _Builder()
    queue: deque[tuple[tuple[str, ...], Mapping[str, Any]]] = deque([((), payload)])
    while queue:
        path, mapping = queue.popleft()
        for raw_key, value in mapping.items():
            key_path = (*path, str(raw_key))
            field = _match(key_path)
            if field is not None and builder.accept(field, value, key_path):
                continue
            if isinstance(value, Mapping):
                queue.append((key_path, value))
            elif value is not None:
                builder.keep_extra(key_path, value)
    return builder.build()


def _match(key_path: tuple[str, ...]) -> str | None:
    field = _FIELD_BY_ALIAS.get(canonical_key(key_path[-1]))
    if field is None and len(key_path) > 1:
        field = _FIELD_BY_ALIAS.get(canonical_key(key_path[-2] + key_path[-1]))
    return field


class _Builder:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.extra: dict[str, Any] = {}
        self.inferred_currency: str | None = None

    def accept(self, field: str, value: Any, key_path: tuple[str, ...]) -> bool:
        if field in self.values:
            return False
        label = ".".join(key_path)
        coerced: Any
        if field == "image_url":
            coerced = _image_url(value)
        elif field == "color":
            coerced = _colors(value, label)
        elif field == "purchase_price":
            coerced = self._purchase_price(value, label)
        elif field == "currency":
            coerced = _currency(value, label)
        else:
            coerced = _text(value, label, _TEXT_LIMITS[field])
        if coerced is None:
            return False
        self.values[field] = coerced
        return True

    def keep_extra(self, key_path: tuple[str, ...], value: Any) -> None:
        if len(self.extra) < _MAX_EXTRA_FIELDS:
            self.extra[".".join(key_path)] = value

    def build(self) -> AnalysisInput:
        values = dict(self.values)
        variant = values.get("special_variant")
        if isinstance(variant, str) and canonical_key(variant) in _STANDARD_VARIANTS:
            values.pop("special_variant")
        values.setdefault("currency", self.inferred_currency)

        if not values.get("image_url") and not (values.get("brand") and values.get("model")):
            raise InvalidRequestError(
                "Provide an image URL (e.g. `image_url`), or at least `brand` and `model`."
            )
        return AnalysisInput(**values, extra=self.extra)

    def _purchase_price(self, value: Any, label: str) -> Decimal | None:
        currency: str | None = None
        if isinstance(value, Mapping):
            currency = _currency(value.get("currency"), f"{label}.currency")
            value = next((value[k] for k in _PRICE_AMOUNT_KEYS if value.get(k) is not None), None)
        amount: Decimal | None = None
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int | float):
            try:
                amount = Decimal(str(value))
            except InvalidOperation:
                return None
        elif isinstance(value, str):
            match = _AMOUNT.search(value)
            amount = parse_amount(match.group().lstrip("-")) if match else None
            if amount is not None and match and match.group().startswith("-"):
                amount = -amount
            currency = currency or detect_currency(value)
        if amount is None:
            return None
        if amount < 0:
            raise InvalidRequestError(f"`{label}` must not be negative")
        if currency:
            self.inferred_currency = currency
        return amount


def _text(value: Any, label: str, limit: int) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        text = str(int(value)) if value.is_integer() else str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    if len(text) > limit:
        raise InvalidRequestError(f"`{label}` must be at most {limit} characters")
    return text or None


def _image_url(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        return next((url for item in value if (url := _image_url(item))), None)
    if isinstance(value, Mapping):
        return next((url for key in _URL_KEYS if (url := _image_url(value.get(key)))), None)
    return None


def _colors(value: Any, label: str) -> list[str] | None:
    items: list[Any]
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = value
    else:
        return None
    colors = [c for item in items if (c := _text(item, label, _COLOR_LIMIT))]
    if len(colors) > _MAX_COLORS:
        raise InvalidRequestError(f"`{label}` accepts at most {_MAX_COLORS} colors")
    return colors or None


def _currency(value: Any, label: str) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{3}", value.strip()):
        return value.strip().upper()
    raise InvalidRequestError(f"`{label}` must be a 3-letter ISO currency code")
