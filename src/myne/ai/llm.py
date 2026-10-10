import base64
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from myne.core.errors import UpstreamServiceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImageInput:
    data: bytes
    mime_type: str = "image/jpeg"

    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{base64.b64encode(self.data).decode('ascii')}"


class StructuredLLM(Protocol):
    """A model that returns a validated instance of `schema` or raises UpstreamServiceError."""

    name: str

    async def generate[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        images: Sequence[ImageInput] = (),
    ) -> T: ...

    async def aclose(self) -> None: ...


class FallbackLLM:
    def __init__(self, primary: StructuredLLM, fallback: StructuredLLM) -> None:
        self._primary = primary
        self._fallback = fallback
        self.name = f"{primary.name}->{fallback.name}"

    async def generate[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        images: Sequence[ImageInput] = (),
    ) -> T:
        try:
            return await self._primary.generate(
                system=system, prompt=prompt, schema=schema, images=images
            )
        except UpstreamServiceError as exc:
            logger.warning(
                "Primary LLM failed, falling back",
                extra={"ctx": {"primary": self._primary.name, "error": exc.detail}},
            )
            return await self._fallback.generate(
                system=system, prompt=prompt, schema=schema, images=images
            )

    async def aclose(self) -> None:
        await self._primary.aclose()
        await self._fallback.aclose()
