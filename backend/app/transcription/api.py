"""Authenticated, bounded native PCM relay. No database transcript/audio persistence."""

import asyncio
import time
from contextlib import suppress
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from websockets.exceptions import ConnectionClosed

from app.core import auth
from app.core.timing import emit
from app.db.auth_repository import AuthRepository
from app.transcription.provider import ProviderError, get_provider

KEEPALIVE_SECONDS = 3
AUTH_RECHECK_SECONDS = 60

router = APIRouter(prefix="/transcription", tags=["transcription"])


def session_valid(application, token: str) -> bool:
    # Short-lived DB session per validation; never hold a transaction during a meeting.
    with application.state.session_factory() as database:
        return auth.authenticated_user(AuthRepository(database), token) is not None


async def error(socket, message, retryable=False):
    await socket.send_json({"type": "error", "message": message, "retryable": retryable})


async def relay(socket, provider, source):
    finished = asyncio.Event()
    stream_id = uuid4().hex
    last_packet_at = None
    packet_count = 0

    async def upload():
        nonlocal last_packet_at, packet_count
        while True:
            message = await socket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()
            pcm = message.get("bytes")
            if pcm is not None:
                if not pcm or len(pcm) > 6400 or len(pcm) % 2:
                    raise ProviderError("Invalid audio packet. Restart the desktop session.", False)
                last_packet_at = time.perf_counter()
                packet_count += 1
                await asyncio.wait_for(provider.send_audio(pcm), timeout=3)
            elif message.get("text") == '{"type":"finish"}':
                await provider.finish()
                finished.set()
                return
            else:
                raise ProviderError("Invalid streaming control message.", False)

    async def download():
        while True:
            event = await provider.receive()
            if event is not None:
                emitted_at = time.perf_counter()
                if event.final and socket.app.state.settings.app_env != "production":
                    emit(
                        {
                            "stage": "transcription_final_emitted",
                            "stream_id": stream_id,
                            "source": source,
                            "segment": event.segment,
                            "at_unix_ms": round(time.time() * 1000),
                            "provider_final_to_normalized_emit_ms": round(
                                (emitted_at - event.provider_received_at) * 1000, 3
                            )
                            if event.provider_received_at is not None
                            else None,
                            "last_packet_to_final_ms": round(
                                (emitted_at - last_packet_at) * 1000, 3
                            )
                            if last_packet_at
                            else None,
                            "packet_count": packet_count,
                        }
                    )
                await socket.send_json(
                    {
                        "type": "transcript",
                        "source": source,
                        "stream_id": stream_id,
                        "segment": event.segment,
                        "text": event.text,
                        "final": event.final,
                    }
                )

    async def maintain():
        checked = asyncio.get_running_loop().time()
        while True:
            await asyncio.sleep(KEEPALIVE_SECONDS)
            if finished.is_set():
                return
            await asyncio.wait_for(provider.keepalive(), timeout=3)
            if asyncio.get_running_loop().time() - checked >= AUTH_RECHECK_SECONDS:
                checked = asyncio.get_running_loop().time()
                if not await run_in_threadpool(
                    session_valid, socket.app, socket.state.session_token
                ):
                    raise ProviderError(
                        "Your MeetGuide session expired or was revoked. Sign in again.", False
                    )

    tasks = [
        asyncio.create_task(upload()),
        asyncio.create_task(download()),
        asyncio.create_task(maintain()),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                task.result()
            except ConnectionClosed:
                if not finished.is_set():
                    raise
        if finished.is_set():
            try:
                await asyncio.wait_for(tasks[1], timeout=2)
            except TimeoutError, ConnectionClosed:
                pass
            await socket.send_json({"type": "done"})
        else:
            raise ProviderError("Transcription connection ended. Reconnecting.")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@router.websocket("/stream")
async def stream(socket: WebSocket):
    await socket.accept()
    provider = None
    try:
        authorization = socket.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if (
            socket.headers.get("origin") is not None
            or scheme.lower() != "bearer"
            or not auth.valid_token(token)
        ):
            raise ProviderError("A native MeetGuide session is required. Sign in again.", False)
        if not await run_in_threadpool(session_valid, socket.app, token):
            raise ProviderError(
                "Your MeetGuide session expired or was revoked. Sign in again.", False
            )
        source = socket.query_params.get("source")
        if source not in {"system", "microphone"}:
            raise ProviderError("Invalid transcription source.", False)
        socket.state.session_token = token
        adapter = get_provider(socket.app.state.settings)
        provider = await adapter.connect()
        await socket.send_json({"type": "ready", "source": source})
        await relay(socket, provider, source)
    except ProviderError as problem:
        with suppress(Exception):
            await error(socket, str(problem), problem.retryable)
    except SQLAlchemyError:
        with suppress(Exception):
            await error(socket, "Session validation is temporarily unavailable.", True)
    except WebSocketDisconnect, asyncio.CancelledError:
        pass
    except Exception:
        # Never send or log provider exceptions, payloads, headers or audio.
        with suppress(Exception):
            await error(socket, "Streaming transcription was interrupted. Reconnecting.", True)
    finally:
        if provider is not None:
            with suppress(Exception):
                await asyncio.wait_for(provider.close(), timeout=2)
        with suppress(Exception):
            await socket.close()
