"""Classify autobiographical assertions inside structured current-solution output.

Field semantics supply the default: code, approach, complexity and spoken solution
explain this generated artifact. First person and grammatical tense alone do not
turn that artifact into the user's biography. Explicit biography anchors do.
No content is logged; diagnostics expose field, sentence index and fixed rule only.
"""

import re
from dataclasses import dataclass

from app.cues.grounding import grounding_issue

PERSON = re.compile(r"\b(?:i|we|my|our)\b|\bi['’](?:ve|m|d)\b", re.I)
BIOGRAPHY = {
    "employment": re.compile(
        r"\b(?:my|our)\s+(?:(?:current|previous|last|former)\s+)?"
        r"(?:role|job|company|employer|career|team|client)\b|"
        r"\b(?:previous|current|former|past)\s+(?:company|job|role|employer|project)\b|"
        r"\b(?:professionally|employment|employed)\b",
        re.I,
    ),
    "experience": re.compile(
        r"\b(?:experience|expertise|background|certified|certification|degree)\b|"
        r"\b(?:years?|months?)\b|\b(?:many|several)\s+times\s+before\b|"
        r"\b(?:solved|built|implemented|used|worked).{0,80}\bbefore\b",
        re.I,
    ),
    "organization": re.compile(
        r"\b(?i:at|for|with)\s+(?:[A-Z][a-zA-Z&-]{2,})(?![\w])|"
        r"\b(?:worked|employed)\s+(?:at|for|by)\b"
    ),
    "achievement": re.compile(r"\b(?:won|earned|awarded|promoted|single-handedly|solely)\b", re.I),
}


@dataclass(frozen=True)
class Rejection:
    field: str
    sentence_index: int
    rule: str
    reason: str


def inspect_fields(fields, evidence):
    for field in ("approach", "code", "complexity", "what_to_say"):
        for index, sentence in enumerate(re.split(r"(?<=[.!?])\s+|\n", fields.get(field) or "")):
            if not PERSON.search(sentence):
                continue
            rule = next(
                (name for name, pattern in BIOGRAPHY.items() if pattern.search(sentence)), None
            )
            if rule is None:
                continue
            issue = grounding_issue(sentence, evidence, personal_claim=True)
            if issue:
                return Rejection(field, index, rule, issue)
    return None
