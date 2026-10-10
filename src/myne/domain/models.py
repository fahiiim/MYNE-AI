from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

from myne.domain.text import dedupe_words, normalize_text

Amount = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
CurrencyCode = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{3}$")
]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
OptionalLabel = Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=80)]


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
    distinctive_features: list[str]
    visible_text: list[str]
    confidence: float


class BagIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    brand: str = Field(min_length=1, max_length=80, examples=["Hermès"])
    model: str = Field(min_length=1, max_length=120, examples=["Birkin"])
    size: OptionalLabel = Field(default=None, examples=["30"])
    material: OptionalLabel = Field(default=None, examples=["Togo leather"])
    color: OptionalLabel = Field(default=None, examples=["Gold"])
    hardware: OptionalLabel = Field(default=None, examples=["Gold hardware"])

    @property
    def display_name(self) -> str:
        return dedupe_words(" ".join(p for p in (self.brand, self.model, self.size) if p))

    def search_query(self) -> str:
        return self.display_name

    def descriptive_query(self) -> str:
        parts = (self.brand, self.model, self.size, self.material, self.color)
        return dedupe_words(" ".join(p for p in parts if p))

    def cache_key(self) -> str:
        fields = (self.brand, self.model, self.size, self.material, self.color, self.hardware)
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


class Appraisal(BaseModel):
    identification: IdentificationResult
    prices: PriceReport | None = Field(
        description="Null when identification needs user confirmation before pricing."
    )
