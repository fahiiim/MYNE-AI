"""Server-Sent Events bridge for long-running operations that report progress."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

from fastapi.encoders import jsonable_encoder

from myne.api.errors import problem_from_exception
from myne.core.errors import MyneError
from myne.services.progress import AnalysisStage, ProgressCallback

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

logger = logging.getLogger(__name__)

_DONE = object()


def format_event(event: str, data: Any) -> str:
    payload = json.dumps(jsonable_encoder(data), separators=(",", ":"), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def stream_with_progress(
    operation: Callable[[ProgressCallback], Awaitable[Any]],
    *,
    instance: str,
    keepalive_seconds: float,
) -> AsyncIterator[str]:
    """Run `operation` in the background and yield its progress as SSE frames.

    Emits `stage` events, then exactly one terminal `result` or `error` event.
    Comment frames keep idle connections alive through proxies. If the client
    disconnects, the generator is closed and the operation is cancelled.
    """
    queue: asyncio.Queue[object] = asyncio.Queue()

    async def on_progress(stage: AnalysisStage, payload: dict[str, Any]) -> None:
        await queue.put(format_event("stage", {"stage": stage.value, **payload}))

    async def run() -> None:
        try:
            result = await operation(on_progress)
            await queue.put(format_event("result", result))
        except MyneError as exc:
            await queue.put(format_event("error", problem_from_exception(exc, instance=instance)))
        except Exception as exc:
            logger.exception("Streamed operation failed")
            await queue.put(format_event("error", problem_from_exception(exc, instance=instance)))
        finally:
            await queue.put(_DONE)

    task = asyncio.create_task(run())
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if frame is _DONE:
                break
            yield str(frame)
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
