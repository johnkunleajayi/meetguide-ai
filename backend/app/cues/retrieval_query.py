"""Local query expansion for broad interview introductions, never scope expansion."""

import re

from app.cues.domain import CueInput

INTRODUCTION = re.compile(
    r"(?:(?:please|can you|could you|would you) )?"
    r"(?:tell (?:me|us) (?:a (?:little|bit) )?about yourself|introduce yourself|"
    r"(?:walk|take) (?:me|us) through your (?:resume|cv|background|career)|"
    r"give (?:me|us) (?:a |an )?(?:brief )?overview of your (?:background|career|experience))"
)
PROFILE_TERMS = (
    "professional summary profile background career employment skills qualifications education"
)


def retrieval_query(payload: CueInput) -> str:
    # Preserve the existing bounded follow-up topic query for other requests.
    previous = " ".join(turn.text for turn in payload.context)[-1200:]
    query = payload.question + " " + previous
    scope = payload._preparation
    normalized = " ".join(re.findall(r"[^\W_]+", payload.question.casefold()))
    if scope and scope.purpose == "job_interview" and INTRODUCTION.fullmatch(normalized):
        # The objective provides topic terms, not evidence or asserted personal facts.
        query += " " + scope.objective + " " + PROFILE_TERMS
    return query
