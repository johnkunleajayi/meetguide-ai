"""High-precision tripwires, not a semantic entailment or paraphrase judge.

Absence of a flag is not proof of truth. The grounded generation prompt is the
primary control; these checks catch concrete unsupported anchors in actual history.
"""

import re

from app.cues.domain import Evidence

TECHNOLOGIES = (
    "Salesforce",
    "SAP",
    "S/4HANA",
    "Oracle",
    "Workday",
    "ServiceNow",
    "HubSpot",
    "Dynamics",
    "AWS",
    "Azure",
    "Kubernetes",
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "React",
    "PostgreSQL",
    "Snowflake",
    "MuleSoft",
)
HISTORY = re.compile(
    r"\b(?:i|we)\s+(?:(?:have|had)\s+)?(?:(?:single-handedly|solely)\s+)?"
    r"(?:worked|built|developed|implemented|integrated|managed|led|delivered|achieved|"
    r"reduced|increased|saved|earned|won|owned|designed|oversaw|used|was|were)\b|"
    r"\b(?:my|our)\s+(?:experience|background|expertise)\s+(?:with|in|at)\b|"
    r"\bi['’]ve\s+\w+",
    re.I,
)


METRIC = re.compile(
    r"\b\d+(?:[,.]\d+)*\s*(?:%|percent\b|years?\b|months?\b|million\b|"
    r"billion\b|users?\b|customers?\b|projects?\b|people\b|engineers?\b)|"
    r"[$£€]\s*\d+(?:[,.]\d+)*",
    re.I,
)
# Explicit named employment/project assertions, not arbitrary capitalized words.
NAMED = re.compile(
    r"\b(?:worked (?:at|for)|employed by|my employer was|project (?:called|named))\s+"
    r"([A-Z][\w&-]*(?:\s+[A-Z][\w&-]*){0,3})"
)


def canonical(text: str) -> str:
    return " ".join(text.casefold().replace("’", "'").split())


def metric_key(value: str) -> str:
    return canonical(value).replace("percent", "%").replace(" ", "").replace(",", "")


def grounding_issue(
    answer: str, evidence: list[Evidence], *, personal_claim: bool = False
) -> str | None:
    source = canonical(" ".join(item.text for item in evidence))
    for sentence in re.split(r"(?<=[.!?])\s+", answer):
        # A hypothetical approach or acknowledgement is not a claim of actual experience.
        history = personal_claim or bool(HISTORY.search(sentence))
        if not history:
            continue
        if not evidence:
            return "Personal history without evidence"
        if personal_claim:
            tenure = re.search(
                r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|several)"
                r"\s+(?:years?|months?)\b",
                sentence,
                re.I,
            )
            if tenure and canonical(tenure.group()) not in source:
                return "Unsupported numeric fact"
        for technology in TECHNOLOGIES:
            pattern = r"(?<!\w)" + re.escape(technology) + r"(?!\w)"
            # Use named casing for technology names that are also everyday English.
            flags = 0 if technology in {"React", "Dynamics", "Workday", "Oracle"} else re.I
            if re.search(pattern, sentence, flags) and not re.search(pattern, source, re.I):
                return "Unsupported technology"
        names = NAMED.findall(sentence)
        if personal_claim:
            names += re.findall(r"\b(?i:at|for|with)\s+([A-Z][a-zA-Z&-]{2,})", sentence)
        for name in names:
            if canonical(name) not in source:
                return "Unsupported named fact"
        for metric in METRIC.findall(sentence):
            if metric_key(metric) not in {metric_key(value) for value in METRIC.findall(source)}:
                return "Unsupported numeric fact"
        # Only unmistakable sole-credit inflation, not verb synonym matching.
        if re.search(
            r"\b(?:single-handedly|solely|sole person)\b", sentence, re.I
        ) and not re.search(r"\b(?:single-handedly|solely|sole person)\b", source):
            return "Unsupported sole credit"
    return None
