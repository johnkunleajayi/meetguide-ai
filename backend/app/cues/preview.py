"""Provisional complete sentences only; final Draft validation is still mandatory."""

import re

from pydantic_core import from_json

from app.cues.grounding import grounding_issue


def preview(raw, evidence):
    try:
        value = from_json(raw, allow_partial="trailing-strings")
    except ValueError:
        return ""
    paragraphs = value.get("paragraphs", []) if isinstance(value, dict) else []
    if not isinstance(paragraphs, list):
        return ""
    complete = []
    for paragraph in paragraphs[:3]:
        if not isinstance(paragraph, str):
            return ""
        # Never release an unfinished factual claim / escaped JSON string fragment.
        ends = list(re.finditer(r"[.!?](?=\s|$)", paragraph))
        if not ends:
            break
        complete.append(paragraph[: ends[-1].end()].strip())
    text = "\n\n".join(complete)
    if not evidence and any(
        not re.match(r"^(?:I would|I'd|I can(?:not|'t)|I do not|I don't)\b", sentence, re.I)
        for sentence in re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
        if sentence.strip()
    ):
        return ""
    if len(text) > 2400 or grounding_issue(text, evidence):
        return ""
    if any(re.match(r"^\s*([-*#•]|\d+[.)])", p) for p in complete):
        return ""
    if re.search(r"\b(you should|you could|mention your|explain your|describe your)\b", text, re.I):
        return ""
    return text
