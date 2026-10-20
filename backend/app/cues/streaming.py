"""Authenticated NDJSON response with bounded backpressure and disconnect cleanup."""

import asyncio
import json
import time

import anyio
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.api.auth import NO_STORE
from app.core.timing import current
from app.cues.provider import ProviderUnavailable
from app.cues.service import generate_cue, retrieve_evidence
from app.cues.stream_timing import mark


def response(payload, user, repository, provider, timing, pending, attempt):
    released = False

    def release():
        nonlocal released
        if not released:
            released = True
            pending[user.id] -= 1
            if not pending[user.id]:
                del pending[user.id]

    async def body():
        queue = asyncio.Queue(maxsize=4)
        timing.values.update(
            live_cue_streaming=True, live_cue_first_output_at=None, attempt=attempt
        )
        token = current.set(timing)

        async def emit(event):
            await queue.put((event, timing.values.get("generation_attempt_count", 1)))

        async def work():
            try:
                with timing.measure("retrieval_ms"):
                    evidence = await run_in_threadpool(
                        retrieve_evidence, repository, user.id, payload
                    )
                timing.values.update(
                    retrieved_excerpt_count=len(evidence),
                    retrieved_context_char_count=sum(len(e.text) for e in evidence),
                )
                result = await asyncio.wait_for(
                    generate_cue(provider, payload, evidence, emit), timeout=27
                )
                timing.values["live_cue_completed_at"] = round(time.time() * 1000)
                await emit(
                    {
                        "type": "ready",
                        "result": result.model_dump(mode="json"),
                        "backend_processing_ms": round(
                            (time.perf_counter() - timing.started) * 1000, 3
                        ),
                    }
                )
            except (SQLAlchemyError, ProviderUnavailable, TimeoutError) as error:
                timing.values["provider_error_type"] = (
                    error.reason
                    if isinstance(error, ProviderUnavailable)
                    else "TIMEOUT"
                    if isinstance(error, TimeoutError)
                    else "DATABASE_ERROR"
                )
                timing.values["provider_http_status"] = getattr(error, "status", None)
                await emit({"type": "error"})
            except Exception:
                timing.values["provider_error_type"] = "STREAM_ERROR"
                await emit({"type": "error"})

        task = asyncio.create_task(work())
        terminal = False
        try:
            while True:
                event, generation_attempt = await queue.get()
                terminal = event["type"] in {"ready", "error"}
                if event["type"] == "partial":
                    mark("first_ndjson_partial_yielded", generation_attempt)
                yield (
                    json.dumps(
                        {**event, "question_id": timing.values["question_id"], "attempt": attempt},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                if event["type"] in {"ready", "error"}:
                    break
        finally:
            if not terminal:
                timing.values.setdefault("provider_error_type", "CLIENT_DISCONNECTED")
            if not task.done():
                task.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(task, return_exceptions=True)
            timing.values.setdefault("live_cue_completed_at", round(time.time() * 1000))
            timing.finish()
            current.reset(token)
            release()

    return StreamingResponse(
        body(),
        media_type="application/x-ndjson",
        headers={
            **NO_STORE,
            "X-Accel-Buffering": "no",
            "X-MeetGuide-Question-Id": timing.values["question_id"],
        },
        background=BackgroundTask(release),
    )
