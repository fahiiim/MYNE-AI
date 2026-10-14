import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

from myne.domain.text import dedupe_words, normalize_text

Amount = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
CurrencyCode = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{3}$")
]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
OptionalLabel = Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=120)]

_QUERY_NOISE = re.compile(r"[()\[\]{}/,;:|]|\b(?:cm|mm|inch(?:es)?)\b\.?", re.IGNORECASE)


def _query_text(*parts: str | None) -> str:
    """Search-engine text: drops brackets, separators and size units ('31 cm (PM)' -> '31 PM')."""
    return dedupe_words(_QUERY_NOISE.sub(" ", " ".join(p for p in parts if p)))


class Condition(StrEnum):
    NEW = "new"
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    UNKNOWN = "unknown"


class MarketSegment(StrEnum):
    RETAIL = "retail"
    RESALE = "resale"


class MatchQuality(StrEnum):
    EXACT = "exact"
    PARTIAL = "partial"


class EvidenceSource(StrEnum):
    VISION_LABEL = "vision_label"
    VISION_ENTITY = "vision_entity"
    VISION_LOGO = "vision_logo"
    VISION_PAGE = "vision_page"
    LENS = "google_lens"
    WEB_SEARCH = "web_search"


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Amount = Field(gt=0)
    currency: CurrencyCode


class BagAttributes(BaseModel):
    """Visual attributes extracted by the vision LLM.

    Also used as the LLM's structured-output schema, so it must stay free of
    defaults and numeric constraints that strict JSON-schema modes reject.
    """

    is_handbag: bool
    brand: str | None
    model_family: str | None
    size: str | None
    material: str | None
    color: str | None
    hardware: str | None
    apparent_condition: str | None
    distinctive_features: list[str]
    visible_text: list[str]
    confidence: float


class BagIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    size: OptionalLabel = None
    material: OptionalLabel = None
    color: OptionalLabel = None
    hardware: OptionalLabel = None
    construction: OptionalLabel = None
    variant: OptionalLabel = None

    @property
    def display_name(self) -> str:
        parts = (self.brand, self.model, self.size, self.variant)
        return dedupe_words(" ".join(p for p in parts if p))

    def search_query(self) -> str:
        return _query_text(self.brand, self.model, self.size, self.variant)

    def model_query(self) -> str:
        return _query_text(self.brand, self.model)

    def descriptive_query(self) -> str:
        return _query_text(
            self.brand,
            self.model,
            self.size,
            self.variant,
            self.construction,
            self.material,
            self.color,
        )

    def cache_key(self) -> str:
        fields = (
            self.brand,
            self.model,
            self.size,
            self.material,
            self.color,
            self.hardware,
            self.construction,
            self.variant,
        )
        return "|".join(normalize_text(f or "") for f in fields)


class Evidence(BaseModel):
    source: EvidenceSource
    title: str
    url: str | None = None
    thumbnail_url: str | None = None
    detail: str | None = None


class BagCandidate(BaseModel):
    identity: BagIdentity
    confidence: Confidence
    rationale: str
    evidence: list[Evidence]


class IdentificationResult(BaseModel):
    image_sha256: str
    attributes: BagAttributes
    candidates: list[BagCandidate]
    needs_confirmation: bool = Field(
        description="True when the client should ask the user to pick or correct the model."
    )
    warnings: list[str]


class PriceObservation(BaseModel):
    source: str
    seller: str | None
    segment: MarketSegment
    condition: Condition
    match: MatchQuality
    title: str
    url: str | None
    original_price: Money
    amount: Amount
    observed_on: date
    live: bool


class PriceStats(BaseModel):
    sample_size: int
    median: Amount
    p25: Amount
    p75: Amount
    low: Amount
    high: Amount


class SegmentPrice(BaseModel):
    segment: MarketSegment
    stats: PriceStats
    by_condition: dict[Condition, PriceStats]
    listings: list[PriceObservation]


class MonthlyPricePoint(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    stats: PriceStats | None
    sources: list[str]


class PriceSeries(BaseModel):
    segment: MarketSegment
    months_with_data: int
    points: list[MonthlyPricePoint]


class SourceStatus(BaseModel):
    name: str
    ok: bool
    results: int = 0
    error: str | None = None


class PriceReport(BaseModel):
    identity: BagIdentity
    currency: CurrencyCode
    generated_at: datetime
    current: list[SegmentPrice]
    history: list[PriceSeries]
    sources: list[SourceStatus]
    warnings: list[str]


class ValuationBasis(StrEnum):
    CONDITION = "condition"
    ALL_CONDITIONS = "all_conditions"
    RETAIL = "retail"
    NONE = "none"


class Valuation(BaseModel):
    condition: Condition
    basis: ValuationBasis = Field(
        description="Which listings the estimate is derived from, most to least specific."
    )
    currency: CurrencyCode
    estimate: PriceStats | None
    purchase_price: Amount | None
    gain: Amount | None = Field(description="Median estimate minus purchase price.")
    gain_percent: float | None


class AnalysisMode(StrEnum):
    IMAGE = "image"
    IMAGE_WITH_DETAILS = "image_with_details"
    DETAILS = "details"


class AnalysisInput(BaseModel):
    """Canonical form of whatever JSON the caller sent."""

    image_url: str | None = None
    user_id: str = "anonymous"
    brand: str | None = None
    model: str | None = None
    condition: str | None = None
    size: str | None = None
    leather: str | None = None
    color: list[str] = Field(default_factory=list)
    hardware: str | None = None
    construction: str | None = None
    special_variant: str | None = None
    purchase_price: Amount | None = None
    currency: CurrencyCode | None = None
    search_query: str | None = None
    notes: str | None = None
    extra: dict[str, Any] = Field(
        default_factory=dict, description="Unrecognized fields, keyed by their original path."
    )

    @property
    def has_bag_details(self) -> bool:
        details = (
            self.brand,
            self.model,
            self.condition,
            self.size,
            self.leather,
            self.hardware,
            self.construction,
            self.special_variant,
        )
        return any(details) or bool(self.color)


class BagAnalysis(BaseModel):
    mode: AnalysisMode
    user_id: str
    currency: CurrencyCode
    generated_at: datetime
    input: AnalysisInput
    bag: BagIdentity | None = Field(
        description="The bag that was priced: identified candidate merged with caller details."
    )
    identification: IdentificationResult | None = Field(
        description="Null in `details` mode, where no image was supplied."
    )
    valuation: Valuation | None
    market_prices: list[SegmentPrice]
    price_history: list[PriceSeries]
    sources: list[SourceStatus]
    warnings: list[str]
