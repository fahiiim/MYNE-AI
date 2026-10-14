from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import StreamingResponse

from myne.api.dependencies import AnalysisServiceDep, SettingsDep
from myne.api.request_normalizer import canonical_key, normalize_request
from myne.api.schemas import BagPriceRequest, ImagePriceRequest
from myne.api.sse import SSE_HEADERS, stream_with_progress
from myne.domain.models import BagAnalysis
from myne.services.progress import ProgressCallback

router = APIRouter(prefix="/bags", tags=["bags"])

_RESERVED_QUERY_KEYS = frozenset({"stream"})

AnalyzeBody = Annotated[
    dict[str, Any] | None,
    Body(
        description=(
            "Any JSON object. Field names are matched flexibly (`image_url`, `imageUrl`, "
            "`photo`, `bag.brandName`, ...). Send an image link, bag details, or both; "
            "at minimum an image link or `brand` + `model`. Unknown fields are kept."
        ),
    ),
]
StreamQuery = Annotated[
    bool,
    Query(description="Stream progress as Server-Sent Events instead of a single JSON reply."),
]


@router.post(
    "/analyze",
    response_model=BagAnalysis,
    summary="Identify a handbag and return its current price and price history",
    responses={
        200: {
            "description": (
                "JSON `BagAnalysis`, or with `stream=true` a `text/event-stream` of `stage` "
                "events followed by one `result` (BagAnalysis) or `error` (problem+json) event."
            ),
            "content": {"text/event-stream": {}},
        }
    },
)
async def analyze_bag(
    request: Request,
    analysis: AnalysisServiceDep,
    settings: SettingsDep,
    body: AnalyzeBody = None,
    stream: StreamQuery = False,
) -> BagAnalysis | StreamingResponse:
    query = {
        key: value
        for key, value in request.query_params.items()
        if canonical_key(key) not in _RESERVED_QUERY_KEYS
    }
    analysis_input = normalize_request({**query, **(body or {})})

    if not stream:
        return await analysis.analyze(analysis_input)

    async def operation(progress: ProgressCallback) -> BagAnalysis:
        return await analysis.analyze(analysis_input, progress=progress)

    return StreamingResponse(
        stream_with_progress(
            operation,
            instance=request.url.path,
            keepalive_seconds=settings.sse_keepalive_seconds,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post(
    "/price/by-image",
    response_model=BagAnalysis,
    summary="Identify a handbag from an image URL, then price it",
)
async def price_by_image(
    analysis: AnalysisServiceDep,
    body: ImagePriceRequest,
) -> BagAnalysis:
    return await analysis.analyze(body.to_input())


@router.post(
    "/price",
    response_model=BagAnalysis,
    summary="Price a handbag from its details",
)
async def price_bag(
    analysis: AnalysisServiceDep,
    body: BagPriceRequest,
) -> BagAnalysis:
    return await analysis.analyze(body.to_input())
