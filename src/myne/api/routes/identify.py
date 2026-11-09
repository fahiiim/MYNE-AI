from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import HttpUrl

from myne.api.dependencies import AnalysisServiceDep, SettingsDep
from myne.api.schemas import IdentifyResponse
from myne.api.sse import SSE_HEADERS, stream_with_progress
from myne.core.errors import InvalidRequestError
from myne.domain.models import BagCandidate, IdentificationResult
from myne.services.progress import ProgressCallback

router = APIRouter(prefix="/identify", tags=["identification"])

ImageUrlQuery = Annotated[
    HttpUrl | None,
    Query(alias="url", description="URL of the image to analyze."),
]
UserIdQuery = Annotated[
    str,
    Query(
        min_length=1,
        max_length=128,
        description="Caller's user id, used for tracing.",
    ),
]
OptionalBody = Annotated[
    dict[str, Any] | None,
    Body(description="Optional JSON body containing `image_url` or `url` and optional `user_id`."),
]


def _response(result: IdentificationResult, *, user_id: str, image_url: str) -> IdentifyResponse:
    return IdentifyResponse.model_validate(
        {**result.model_dump(), "user_id": user_id, "image_url": image_url}
    )


def _extract_url_and_user(
    image_url: HttpUrl | None, user_id: str, body: dict[str, Any] | None
) -> tuple[str, str]:
    url: str | None = str(image_url) if image_url is not None else None
    uid = user_id
    if body:
        if not url:
            raw_url = body.get("image_url") or body.get("url") or body.get("imageUrl")
            if isinstance(raw_url, str) and raw_url.strip():
                url = raw_url.strip()
        if uid == "anonymous":
            body_uid = body.get("user_id") or body.get("userId")
            if isinstance(body_uid, str) and body_uid.strip():
                uid = body_uid.strip()
    if not url:
        raise InvalidRequestError("Provide an image URL (e.g. ?url=... or `image_url` in body).")
    return url, uid


@router.post(
    "/upload",
    response_model=IdentifyResponse,
    summary="Identify a handbag's brand and model from an image URL",
)
@router.post(
    "/search",
    response_model=IdentifyResponse,
    summary="Search / identify a handbag's brand and model from an image URL",
)
async def identify_upload(
    analysis: AnalysisServiceDep,
    image_url: ImageUrlQuery = None,
    user_id: UserIdQuery = "anonymous",
    body: OptionalBody = None,
) -> IdentifyResponse:
    url, uid = _extract_url_and_user(image_url, user_id, body)
    result = await analysis.identify(url)
    return _response(result, user_id=uid, image_url=url)


@router.post(
    "/products",
    response_model=list[BagCandidate],
    summary="Image search returning the searched product list/array directly",
)
@router.get(
    "/products",
    response_model=list[BagCandidate],
    summary="Image search returning the searched product list/array directly",
)
async def search_products(
    analysis: AnalysisServiceDep,
    image_url: ImageUrlQuery = None,
    user_id: UserIdQuery = "anonymous",
    body: OptionalBody = None,
) -> list[BagCandidate]:
    url, _ = _extract_url_and_user(image_url, user_id, body)
    result = await analysis.identify(url)
    return result.candidates


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
@router.post(
    "/search/stream",
    response_class=StreamingResponse,
    summary="Identify a handbag with live progress (Server-Sent Events)",
)
async def identify_upload_stream(
    request: Request,
    analysis: AnalysisServiceDep,
    settings: SettingsDep,
    *,
    image_url: ImageUrlQuery = None,
    user_id: UserIdQuery = "anonymous",
    body: OptionalBody = None,
) -> StreamingResponse:
    url, uid = _extract_url_and_user(image_url, user_id, body)

    async def operation(progress: ProgressCallback) -> IdentifyResponse:
        result = await analysis.identify(url, progress=progress)
        return _response(result, user_id=uid, image_url=url)

    return StreamingResponse(
        stream_with_progress(
            operation,
            instance=request.url.path,
            keepalive_seconds=settings.sse_keepalive_seconds,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
