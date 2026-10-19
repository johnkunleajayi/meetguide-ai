import logging

from app.context.repository import ContextRepository
from app.context.retrieval import LocalLexicalIndex
from app.cues.domain import CueInput, Evidence
from app.cues.prompt import SYSTEM, user_prompt, validate_draft
from app.cues.provider import CueProvider, ProviderUnavailable

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
    # Recent turns carry the subject of short follow-ups, without treating them as facts.
    previous = " ".join(turn.text for turn in payload.context)[-1200:]
    query = payload.question + " " + previous
    ranked = LocalLexicalIndex().rank(query, repository.rows(user_id, None), 3)
    return [
        Evidence(id=f"E{index}", document_id=doc.id, chunk_id=chunk.id, text=chunk.text[:1200])
        for index, (_, doc, chunk) in enumerate(ranked, 1)
    ]


async def generate_cue(provider: CueProvider, payload: CueInput, evidence: list[Evidence]):
    system = SYSTEM
    for attempt in range(2):
        draft = await provider.generate(system, user_prompt(payload, evidence))
        try:
            return validate_draft(draft, evidence)
        except ValueError as error:
            reason = str(error) if str(error) in GROUNDING_REASONS else "VALIDATION_REJECTED"
            # Fixed categories only. No answer/evidence, exception detail or token logging.
            logger.warning("Live Cue validation: attempt=%s reason=%s", attempt + 1, reason)
            if attempt:
                raise ProviderUnavailable() from None
            # One conservative regeneration, not a second LLM judge. The prior output is
            # not resent; both attempts share the API's existing overall deadline/cancellation.
            system = SYSTEM + (
                "\nREGENERATE CONSERVATIVELY: previous output failed a local check: "
                + reason
                + ". Omit uncertain personal details and metrics. Use only clearly supported "
                "experience; acknowledge missing facts and use a general approach for gaps. "
                "Return the required natural spoken paragraphs and valid evidence IDs."
            )
