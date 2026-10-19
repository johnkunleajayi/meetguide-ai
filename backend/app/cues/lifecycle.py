import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from fastapi import Request

T = TypeVar("T")


class CueDisconnected(Exception):
    pass


async def until_disconnect(request: Request, work: Awaitable[T]) -> T:
    stopped = asyncio.Event()

    async def monitor():
        while not stopped.is_set():
            if await request.is_disconnected():
                return True
            try:
                await asyncio.wait_for(stopped.wait(), timeout=0.15)
            except TimeoutError:
                pass
        return False

    task = asyncio.create_task(work)
    disconnected = asyncio.create_task(monitor())
    try:
        done, _ = await asyncio.wait([task, disconnected], return_when=asyncio.FIRST_COMPLETED)
        if disconnected in done and disconnected.result():
            raise CueDisconnected()
        return await task
    finally:
        # Starlette's disconnect probe uses an AnyIO cancellation scope. Stop the monitor
        # cooperatively so cancellation cannot be swallowed inside that scope.
        stopped.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, disconnected, return_exceptions=True)
