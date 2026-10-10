from collections.abc import Sequence

import openai
from openai import AsyncOpenAI
from openai.types.responses import (
    EasyInputMessageParam,
    ResponseInputImageParam,
    ResponseInputMessageContentListParam,
    ResponseInputTextParam,
)
from pydantic import BaseModel

from myne.ai.llm import ImageInput
from myne.core.errors import UpstreamServiceError


class OpenAILLM:
    name = "openai"

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=2)
        self._model = model

    async def generate[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        images: Sequence[ImageInput] = (),
    ) -> T:
        content: ResponseInputMessageContentListParam = [
            ResponseInputTextParam(type="input_text", text=prompt),
            *(
                ResponseInputImageParam(
                    type="input_image", image_url=image.data_url(), detail="high"
                )
                for image in images
            ),
        ]
        message = EasyInputMessageParam(role="user", content=content)
        try:
            response = await self._client.responses.parse(
                model=self._model,
                instructions=system,
                input=[message],
                text_format=schema,
            )
        except openai.OpenAIError as exc:
            raise UpstreamServiceError(self.name, type(exc).__name__) from exc

        parsed = response.output_parsed
        if parsed is None:
            raise UpstreamServiceError(self.name, "no structured output (refusal or truncation)")
        return parsed

    async def aclose(self) -> None:
        await self._client.close()
