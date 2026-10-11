from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any


class IdentificationStage(StrEnum):
    IMAGE_FETCHED = "image_fetched"
    ATTRIBUTES_EXTRACTED = "attributes_extracted"
    EVIDENCE_COLLECTED = "evidence_collected"
    CANDIDATES_RANKED = "candidates_ranked"


ProgressCallback = Callable[[IdentificationStage, dict[str, Any]], Awaitable[None]]


async def emit(
    progress: ProgressCallback | None, stage: IdentificationStage, payload: dict[str, Any]
) -> None:
    if progress is not None:
        await progress(stage, payload)
