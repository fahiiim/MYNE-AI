from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel

from myne.ai.llm import ImageInput
from myne.domain.models import Money
from myne.services.pricing.sources import PriceQuery, RawPrice


class ScriptedLLM:
    """Returns a pre-built response per requested schema and records every call."""

    name = "scripted"

    def __init__(self, responses: dict[type[BaseModel], BaseModel]) -> None:
        self._responses = responses
        self.calls: list[type[BaseModel]] = []

    async def generate[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        images: Sequence[ImageInput] = (),
    ) -> T:
        self.calls.append(schema)
        response = self._responses[schema]
        assert isinstance(response, schema)
        return response

    async def aclose(self) -> None:
        return None


class StaticSource:
    def __init__(self, name: str, prices: list[RawPrice]) -> None:
        self.name = name
        self._prices = prices

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        return self._prices


class FailingSource:
    def __init__(self, name: str, error: Exception) -> None:
        self.name = name
        self._error = error

    async def collect(self, query: PriceQuery) -> list[RawPrice]:
        raise self._error


class FixedRateFx:
    def __init__(self, rates_to_target: dict[str, Decimal]) -> None:
        self._rates = rates_to_target

    async def convert(self, money: Money, target: str) -> Decimal | None:
        if money.currency == target:
            return money.amount
        rate = self._rates.get(money.currency)
        return money.amount * rate if rate is not None else None
