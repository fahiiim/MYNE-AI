import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    field_serializer,
    model_validator,
)

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


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unknown"


class BagCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    rank: int = 1
    brand: str = ""
    brand_id: str = Field(default="", alias="brandId")
    model: str = ""
    model_id: str = Field(default="", alias="modelId")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    confidence: float | int = 0
    estimated_value_eur: int | float | None = Field(default=None, alias="estimatedValueEUR")

    detected_size: str | None = Field(default=None, alias="detectedSize")
    detected_colors: list[str] = Field(default_factory=list, alias="detectedColors")
    detected_hardware: str | None = Field(default=None, alias="detectedHardware")
    detected_leathers: str | None = Field(default=None, alias="detectedLeathers")
    detected_construction: str | None = Field(default=None, alias="detectedConstruction")
    detected_year: str | None = Field(default=None, alias="detectedYear")
    condition: str | None = None

    special_variant: str | None = None
    alternative_colors: list[str] = Field(default_factory=list, alias="alternativeColors")
    image_search_query: str = Field(default="", alias="imageSearchQuery")

    analysis: str = ""

    # Preserved for backward compatibility
    identity: BagIdentity = Field(
        default_factory=lambda: BagIdentity(brand="Unknown", model="Unknown")
    )
    rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list)

    def __getattr__(self, name: str) -> Any:
        mapping = {
            "brandId": "brand_id",
            "modelId": "model_id",
            "thumbnailUrl": "thumbnail_url",
            "estimatedValueEUR": "estimated_value_eur",
            "detectedSize": "detected_size",
            "detectedColors": "detected_colors",
            "detectedHardware": "detected_hardware",
            "detectedLeathers": "detected_leathers",
            "detectedConstruction": "detected_construction",
            "detectedYear": "detected_year",
            "alternativeColors": "alternative_colors",
            "imageSearchQuery": "image_search_query",
        }
        if name in mapping:
            return getattr(self, mapping[name])
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    @field_serializer("confidence", when_used="json")
    def _serialize_confidence(self, value: float | int) -> int:
        if isinstance(value, float) and 0.0 <= value <= 1.0:
            return round(value * 100)
        return round(value)

    @model_validator(mode="before")
    @classmethod
    def _populate_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            identity = data.get("identity")
            ident_dict: dict[str, Any] = {}
            if isinstance(identity, BagIdentity):
                ident_dict = identity.model_dump()
            elif isinstance(identity, dict):
                ident_dict = identity

            if ident_dict:
                data.setdefault("brand", ident_dict.get("brand", ""))
                data.setdefault("model", ident_dict.get("model", ""))
                data.setdefault("detected_size", ident_dict.get("size"))
                data.setdefault("detected_leathers", ident_dict.get("material"))
                data.setdefault("detected_hardware", ident_dict.get("hardware"))
                data.setdefault("detected_construction", ident_dict.get("construction"))
                data.setdefault("special_variant", ident_dict.get("variant"))
                if color := ident_dict.get("color"):
                    data.setdefault(
                        "detected_colors", [c.strip() for c in color.split("/") if c.strip()]
                    )

            brand = data.get("brand", "")
            model = data.get("model", "")
            if brand and not data.get("brand_id") and not data.get("brandId"):
                data["brand_id"] = _slugify(brand)
            if model and not data.get("model_id") and not data.get("modelId"):
                data["model_id"] = _slugify(f"{brand}-{model}" if brand else model)
            if not data.get("analysis") and data.get("rationale"):
                data["analysis"] = data["rationale"]
            if not data.get("rationale") and data.get("analysis"):
                data["rationale"] = data["analysis"]
            if not data.get("image_search_query") and not data.get("imageSearchQuery"):
                colors = data.get("detected_colors") or data.get("detectedColors") or []
                query_parts = [
                    brand,
                    model,
                    data.get("detected_size") or data.get("detectedSize"),
                    data.get("detected_leathers") or data.get("detectedLeathers"),
                    colors[0] if colors else "",
                    data.get("detected_hardware") or data.get("detectedHardware"),
                ]
                data["image_search_query"] = " ".join(p for p in query_parts if p)

            if not isinstance(identity, BagIdentity) and brand and model:
                colors = data.get("detected_colors") or data.get("detectedColors") or []
                color_str = " / ".join(colors) or None
                data["identity"] = BagIdentity(
                    brand=brand,
                    model=model,
                    size=data.get("detected_size") or data.get("detectedSize"),
                    material=data.get("detected_leathers") or data.get("detectedLeathers"),
                    color=color_str,
                    hardware=data.get("detected_hardware") or data.get("detectedHardware"),
                    construction=data.get("detected_construction")
                    or data.get("detectedConstruction"),
                    variant=data.get("special_variant"),
                )
        return data


class IdentificationResult(BaseModel):
    image_sha256: str
    attributes: BagAttributes
    candidates: list[BagCandidate]
    products: list[BagCandidate] = Field(
        default_factory=list,
        description="Searched product list in the standardized product structure.",
    )
    needs_confirmation: bool = Field(
        description="True when the client should ask the user to pick or correct the model."
    )
    warnings: list[str]

    @model_validator(mode="before")
    @classmethod
    def _sync_products(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "candidates" in data and not data.get("products"):
                data["products"] = data["candidates"]
            elif "products" in data and not data.get("candidates"):
                data["candidates"] = data["products"]
        return data


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
