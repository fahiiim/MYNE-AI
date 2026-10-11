"""Wire contracts agreed with the MYNE backend."""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

from myne.domain.models import BagIdentity, IdentificationResult

_STANDARD_VARIANTS = frozenset({"", "standard", "none", "regular"})

ColorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]


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

    @property
    def purchase_price_decimal(self) -> Decimal | None:
        return _to_decimal(self.purchase_price)


class BagPriceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    condition: str = Field(min_length=1, max_length=60, examples=["Excellent"])
    color: list[ColorName] = Field(default_factory=list, max_length=5)
    leather: str = Field(default="", max_length=60)
    hardware: str = Field(default="", max_length=60)
    size: str = Field(default="", max_length=30)
    construction: str = Field(default="", max_length=60)
    special_variant: str = Field(default="Standard", max_length=60)
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
            return [value] if value.strip() else []
        return value

    @property
    def purchase_price_decimal(self) -> Decimal | None:
        return _to_decimal(self.purchase_price)

    def to_identity(self) -> BagIdentity:
        variant = self.special_variant
        return BagIdentity(
            brand=self.brand,
            model=self.model,
            size=self.size or None,
            material=self.leather or None,
            color=" / ".join(self.color) or None,
            hardware=self.hardware or None,
            construction=self.construction or None,
            variant=None if variant.lower() in _STANDARD_VARIANTS else variant,
        )


def _to_decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
