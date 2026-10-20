"""Content-free development diagnostics. Never accept arbitrary log fields/content."""

import json
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

logger = logging.getLogger("meetguide.timing")
current: ContextVar = ContextVar("meetguide_timing", default=None)


def emit(values):
    logger.warning("[MeetGuide Timing] %s", json.dumps(values, separators=(",", ":")))


class Timing:
    def __init__(self, question_id=None, stage="backend_live_cue", enabled=True):
        self.started = time.perf_counter()
        self.enabled = enabled
        self.values = {
            "question_id": question_id
            if question_id and re.fullmatch(r"q-[a-zA-Z0-9-]{1,80}", question_id)
            else "q-" + uuid4().hex,
            "stage": stage,
            "started_at_unix_ms": round(time.time() * 1000),
        }

    @contextmanager
    def measure(self, name):
        began = time.perf_counter()
        self.values.setdefault(
            name.removesuffix("_ms") + "_started_at_unix_ms", round(time.time() * 1000)
        )
        try:
            yield
        finally:
            self.values[name.removesuffix("_ms") + "_completed_at_unix_ms"] = round(
                time.time() * 1000
            )
            self.values[name] = round(
                self.values.get(name, 0) + (time.perf_counter() - began) * 1000, 3
            )

    def finish(self):
        self.values["backend_total_ms"] = round((time.perf_counter() - self.started) * 1000, 3)
        if self.enabled:
            emit(self.values)

    def headers(self):
        return {
            "X-MeetGuide-Question-Id": self.values["question_id"],
            "X-MeetGuide-Backend-Ms": str(round((time.perf_counter() - self.started) * 1000, 3)),
        }


@contextmanager
def measure(name):
    timing = current.get()
    if timing is None:
        yield
    else:
        with timing.measure(name):
            yield
