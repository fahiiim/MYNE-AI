from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import HttpUrl

from myne.api.dependencies import AppraisalServiceDep, SettingsDep
from myne.api.schemas import IdentifyResponse
from myne.api.sse import SSE_HEADERS, stream_with_progress
from myne.domain.models import IdentificationResult
from myne.services.progress import ProgressCallback

router = APIRouter(prefix="/identify", tags=["identification"])

ImageUrlQuery = Annotated[HttpUrl, Query(alias="url", description="URL of the image to analyze.")]
UserIdQuery = Annotated[
    str,
    Query(min_length=1, max_length=128, description="Caller's user id, used for tracing."),
]


def _response(result: IdentificationResult, *, user_id: str, image_url: str) -> IdentifyResponse:
    return IdentifyResponse.model_validate(
        {**result.model_dump(), "user_id": user_id, "image_url": image_url}
    )


@router.post(
    "/upload",
    response_model=IdentifyResponse,
    summary="Identify a handbag's brand and model from an image URL",
)
async def identify_upload(
    appraisals: AppraisalServiceDep,
    image_url: ImageUrlQuery,
    user_id: UserIdQuery = "anonymous",
) -> IdentifyResponse:
    url = str(image_url)
    result = await appraisals.identify_url(url)
    return _response(result, user_id=user_id, image_url=url)


@router.post(
    "/upload/stream",
    response_class=StreamingResponse,
    summary="Identify a handbag with live progress (Server-Sent Events)",
    responses={
        200: {
            "description": (
                "`stage` events (image_fetched, attributes_extracted, evidence_collected, "
                "candidates_ranked) followed by one `result` (IdentifyResponse) or `error` "
                "(problem+json) event."
            ),
            "content": {"text/event-stream": {}},
        }
    },
)
async def identify_upload_stream(
    request: Request,
    appraisals: AppraisalServiceDep,
    settings: SettingsDep,
    image_url: ImageUrlQuery,
    user_id: UserIdQuery = "anonymous",
) -> StreamingResponse:
    url = str(image_url)

    async def operation(progress: ProgressCallback) -> IdentifyResponse:
        result = await appraisals.identify_url(url, progress=progress)
        return _response(result, user_id=user_id, image_url=url)

    return StreamingResponse(
        stream_with_progress(
            operation,
            instance=request.url.path,
            keepalive_seconds=settings.sse_keepalive_seconds,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
