"""Wire contracts agreed with the MYNE backend."""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

from myne.domain.models import AnalysisInput, IdentificationResult

ColorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class IdentifyResponse(IdentificationResult):
    user_id: str
    image_url: str


class ImagePriceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    image_url: HttpUrl
    image_search_query: str = Field(
        default="",
        max_length=300,
        description="Optional text that refines the reverse-image search (e.g. 'Hermes Kelly').",
    )
    purchase_price: float | None = Field(default=None, ge=0)

    def to_input(self) -> AnalysisInput:
        return AnalysisInput(
            image_url=str(self.image_url),
            search_query=self.image_search_query or None,
            purchase_price=_to_decimal(self.purchase_price),
        )


class BagPriceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    condition: str = Field(min_length=1, max_length=60)
    color: list[ColorName] = Field(default_factory=list, max_length=8)
    leather: str = Field(default="", max_length=120)
    hardware: str = Field(default="", max_length=120)
    size: str = Field(default="", max_length=40)
    construction: str = Field(default="", max_length=120)
    special_variant: str = Field(default="Standard", max_length=120)
    purchase_price: float | None = Field(default=None, ge=0)
    image_search_query: str | None = Field(
        default=None,
        max_length=300,
        description="Optional marketplace search query overriding the generated one.",
    )

    @field_validator("color", mode="before")
    @classmethod
    def _coerce_color(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [c for c in (part.strip() for part in value.split(",")) if c]
        return value

    def to_input(self) -> AnalysisInput:
        variant = self.special_variant
        return AnalysisInput(
            brand=self.brand,
            model=self.model,
            condition=self.condition,
            color=self.color,
            leather=self.leather or None,
            hardware=self.hardware or None,
            size=self.size or None,
            construction=self.construction or None,
            special_variant=None if variant.lower() in _STANDARD_VARIANTS else variant,
            purchase_price=_to_decimal(self.purchase_price),
            search_query=self.image_search_query or None,
        )


_STANDARD_VARIANTS = frozenset({"", "standard", "none", "regular", "n/a"})


def _to_decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
