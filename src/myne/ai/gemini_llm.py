from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from myne.ai.llm import ImageInput
from myne.core.errors import UpstreamServiceError


class GeminiLLM:
    name = "gemini"

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        self._model = model

    async def generate[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        images: Sequence[ImageInput] = (),
    ) -> T:
        contents: list[Any] = [
            types.Part.from_bytes(data=image.data, mime_type=image.mime_type) for image in images
        ]
        contents.append(prompt)
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.1,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model, contents=contents, config=config
            )
        except genai_errors.APIError as exc:
            raise UpstreamServiceError(self.name, f"API error {exc.code}") from exc

        if not response.text:
            raise UpstreamServiceError(self.name, "empty response (safety block or truncation)")
        try:
            return schema.model_validate_json(response.text)
        except ValidationError as exc:
            raise UpstreamServiceError(self.name, "structured output failed validation") from exc

    async def aclose(self) -> None:
        aio_close = getattr(self._client.aio, "aclose", None)
        if aio_close is not None:
            await aio_close()
