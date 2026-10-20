"""Fixed, content-free streaming boundaries; monotonic durations per generation attempt."""

import time

from app.core.timing import current

PAIRS = (
    ("http_request_started", "headers_received"),
    ("headers_received", "first_raw_chunk"),
    ("first_raw_chunk", "first_content_fragment"),
    ("first_content_fragment", "first_displayable_text"),
    ("first_displayable_text", "first_ndjson_partial_yielded"),
    ("first_displayable_text", "generation_completed"),
    ("http_request_started", "generation_completed"),
    ("generation_completed", "validation_completed"),
)
STAGES = frozenset(stage for pair in PAIRS for stage in pair)


def mark(stage, attempt=None):
    timing = current.get()
    if timing is None or stage not in STAGES:
        return
    attempt = attempt or timing.values.get("generation_attempt_count", 1)
    records = timing.values.setdefault("stream_diagnostics", [])
    record = next((item for item in records if item["generation_attempt"] == attempt), None)
    if record is None:
        record = {"generation_attempt": attempt}
        records.append(record)
    # Monotonic instants are private bookkeeping, never serialized as wall-clock times.
    if not hasattr(timing, "_stream_instants"):
        timing._stream_instants = {}
    instants = timing._stream_instants.setdefault(attempt, {})
    if stage in instants:
        return
    instants[stage] = time.perf_counter()
    record[stage + "_at_unix_ms"] = round(time.time() * 1000)
    record[stage + "_offset_ms"] = round((instants[stage] - timing.started) * 1000, 3)
    for start, end in PAIRS:
        if start in instants and end in instants:
            record[start + "_to_" + end + "_ms"] = round(
                (instants[end] - instants[start]) * 1000, 3
            )
    if "first_ndjson_partial_yielded" in instants and "generation_completed" in instants:
        # These are concurrent branches: negative means generation finished before
        # the response iterator handed off its first partial, not a clock error.
        record["ndjson_partial_lead_before_generation_completed_ms"] = round(
            (instants["generation_completed"] - instants["first_ndjson_partial_yielded"]) * 1000,
            3,
        )
