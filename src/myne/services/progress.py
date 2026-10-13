from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any


class AnalysisStage(StrEnum):
    IMAGE_FETCHED = "image_fetched"
    ATTRIBUTES_EXTRACTED = "attributes_extracted"
    EVIDENCE_COLLECTED = "evidence_collected"
    CANDIDATES_RANKED = "candidates_ranked"
    PRICING_STARTED = "pricing_started"
    PRICING_COMPLETED = "pricing_completed"


ProgressCallback = Callable[[AnalysisStage, dict[str, Any]], Awaitable[None]]


async def emit(
    progress: ProgressCallback | None, stage: AnalysisStage, payload: dict[str, Any]
) -> None:
    if progress is not None:
        await progress(stage, payload)
