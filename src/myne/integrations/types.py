from dataclasses import dataclass
from datetime import date

from myne.domain.models import Money


@dataclass(frozen=True, slots=True)
class WebResult:
    title: str
    url: str
    snippet: str
    date_text: str | None
    source: str | None


@dataclass(frozen=True, slots=True)
class MarketListing:
    title: str
    url: str | None
    seller: str | None
    price: Money | None
    condition_hint: str | None


@dataclass(frozen=True, slots=True)
class LensMatch:
    title: str
    url: str | None
    source: str | None
    thumbnail_url: str | None
    price: Money | None


@dataclass(frozen=True, slots=True)
class WebPage:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class WebDetection:
    best_guess_labels: tuple[str, ...]
    entities: tuple[tuple[str, float], ...]
    logos: tuple[tuple[str, float], ...]
    pages: tuple[WebPage, ...]


@dataclass(frozen=True, slots=True)
class ArchiveSnapshot:
    timestamp: str
    original_url: str
    captured_on: date
