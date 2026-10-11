"""RFC 9457 problem+json responses for every error path."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from myne.core.errors import MyneError
from myne.core.logging import request_id_ctx

logger = logging.getLogger(__name__)

_PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem_body(
    *, status: int, code: str, title: str, detail: str, instance: str, **extra: Any
) -> dict[str, Any]:
    return {
        "type": f"urn:myne:error:{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
        "request_id": request_id_ctx.get(),
        **extra,
    }


def problem_from_exception(exc: BaseException, *, instance: str) -> dict[str, Any]:
    if isinstance(exc, MyneError):
        return problem_body(
            status=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            instance=instance,
        )
    return problem_body(
        status=500,
        code="internal_error",
        title="Internal server error",
        detail="An unexpected error occurred.",
        instance=instance,
    )


def _problem(
    request: Request, *, status: int, code: str, title: str, detail: str, **extra: Any
) -> JSONResponse:
    body = problem_body(
        status=status, code=code, title=title, detail=detail, instance=request.url.path, **extra
    )
    return JSONResponse(jsonable_encoder(body), status_code=status, media_type=_PROBLEM_MEDIA_TYPE)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MyneError)
    async def _domain_error(request: Request, exc: MyneError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.warning(
                "Request failed", extra={"ctx": {"code": exc.code, "detail": exc.detail}}
            )
        return _problem(
            request, status=exc.status_code, code=exc.code, title=exc.title, detail=exc.detail
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(
            request,
            status=422,
            code="validation_error",
            title="Request validation failed",
            detail="One or more fields are invalid.",
            errors=exc.errors(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            request,
            status=exc.status_code,
            code="http_error",
            title="HTTP error",
            detail=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return _problem(
            request,
            status=500,
            code="internal_error",
            title="Internal server error",
            detail="An unexpected error occurred.",
        )
