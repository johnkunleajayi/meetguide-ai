import logging
import time

from pydantic import ValidationError

from app.context.repository import ContextRepository
from app.context.retrieval import LocalLexicalIndex
from app.core.timing import current, measure
from app.cues.domain import CueInput, Draft, Evidence
from app.cues.preview import preview
from app.cues.prompt import SYSTEM, user_prompt, validate_draft
from app.cues.provider import CueProvider, ProviderUnavailable
from app.cues.retrieval_query import retrieval_query
from app.cues.stream_timing import mark

logger = logging.getLogger(__name__)
GROUNDING_REASONS = {
    "Unsupported evidence",
    "Invalid spoken length",
    "Invalid paragraph",
    "Coaching is not an answer",
    "Personal history without evidence",
    "Unsupported technology",
    "Unsupported named fact",
    "Unsupported numeric fact",
    "Unsupported sole credit",
}


def retrieve_evidence(repository: ContextRepository, user_id, payload: CueInput) -> list[Evidence]:
    query = retrieval_query(payload)
    scope = payload._preparation
    selections = scope.documents if scope is not None and scope.user_id == user_id else []
    roles = {entry.document_id: entry.context_role for entry in selections}
    rows = repository.scoped_rows(user_id, list(roles)) if roles else []
    ranked = LocalLexicalIndex().rank(
        query, [(doc, chunk) for doc, chunk in rows if doc.id in roles], 3
    )
    return [
        Evidence(
            id=f"E{index}",
            document_id=doc.id,
            chunk_id=chunk.id,
            text=chunk.text[:1200],
            context_role=roles.get(doc.id, "other"),
        )
        for index, (_, doc, chunk) in enumerate(ranked, 1)
    ]


async def generate_cue(
    provider: CueProvider, payload: CueInput, evidence: list[Evidence], emit=None
):
    system = SYSTEM
    stream_started = time.perf_counter()
    for attempt in range(2):
        if timing := current.get():
            timing.values["generation_attempt_count"] = attempt + 1
        with measure("live_cue_generation_ms"):
            if emit is None:
                draft = await provider.generate(system, user_prompt(payload, evidence))
            else:
                if timing := current.get():
                    timing.values.setdefault(
                        "live_cue_request_started_at", round(time.time() * 1000)
                    )
                raw, shown = "", ""
                async for fragment in provider.stream(system, user_prompt(payload, evidence)):
                    raw += fragment
                    if len(raw.encode()) > 16384:
                        raise ProviderUnavailable("RESPONSE_TOO_LARGE")
                    text = preview(raw, evidence)
                    if text and text != shown:
                        mark("first_displayable_text")
                        if timing := current.get():
                            if timing.values.get("live_cue_first_output_at") is None:
                                now = round(time.time() * 1000)
                                timing.values["live_cue_first_output_at"] = now
                                timing.values["live_cue_time_to_first_output_ms"] = (
                                    time.perf_counter() - stream_started
                                ) * 1000
                        await emit({"type": "partial", "answer": text})
                        shown = text
                    elif shown and not text:
                        await emit({"type": "reset"})
                        shown = ""
                mark("generation_completed")
                try:
                    draft = Draft.model_validate_json(raw)
                except ValidationError:
                    raise ProviderUnavailable("RESPONSE_SCHEMA_REJECTED") from None
        try:
            with measure("validation_ms"):
                try:
                    result = validate_draft(draft, evidence)
                finally:
                    if emit is not None:
                        mark("validation_completed")
                return result
        except ValueError as error:
            reason = str(error) if str(error) in GROUNDING_REASONS else "VALIDATION_REJECTED"
            # Fixed categories only. No answer/evidence, exception detail or token logging.
            logger.warning("Live Cue validation: attempt=%s reason=%s", attempt + 1, reason)
            if timing := current.get():
                timing.values["validation_rejection"] = reason
            if emit is not None:
                await emit({"type": "reset"})
            if attempt:
                raise ProviderUnavailable("VALIDATION_REJECTED") from None
            # One conservative regeneration, not a second LLM judge. The prior output is
            # not resent; both attempts share the API's existing overall deadline/cancellation.
            system = SYSTEM + (
                "\nREGENERATE CONSERVATIVELY: previous output failed a local check: "
                + reason
                + ". Omit uncertain personal details and metrics. Use only clearly supported "
                "experience; acknowledge missing facts and use a general approach for gaps. "
                "Return the required natural spoken paragraphs and valid evidence IDs."
            )
