"""Replaceable chunk/index boundary with deterministic BM25 lexical ranking."""

import math
import re
from collections import Counter
from typing import Protocol

from app.models.document import Document, DocumentChunk

STOP = set(
    "a an the and or to of in on at for with is was were be as i we my our your experience".split()
)
GROUPS = [
    (
        "leadership leader leaders lead led leading manage managed manager management "
        "mentor mentoring supervised supervision"
    ),
    (
        "integration integrations integrate integrated integrating api apis "
        "automation automate automated"
    ),
    "project projects",
    "team teams",
    "develop developed development developer",
]
ALIASES = {word: group.split()[0] for group in GROUPS for word in group.split()}


def tokens(text: str) -> list[str]:
    return [
        ALIASES.get(word, word)
        for word in re.findall(r"[^\W_]+", text.casefold())
        if word not in STOP
    ]


def chunk_text(text: str, limit: int = 1200) -> list[str]:
    """Keep paragraphs/lines together; overlap split long paragraphs by 160 characters."""
    result, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) + 2 > limit:
            result.append(current)
            current = ""
        while len(paragraph) > limit:
            split = paragraph.rfind(" ", limit // 2, limit)
            split = split if split > 0 else limit
            result.append(paragraph[:split].strip())
            overlap = max(0, split - 160)
            # Start overlap at a word boundary where possible.
            boundary = paragraph.find(" ", overlap, split)
            paragraph = paragraph[boundary + 1 if boundary >= 0 else overlap :].strip()
        current = current + "\n\n" + paragraph if current else paragraph
    if current:
        result.append(current)
    return result


class RetrievalIndex(Protocol):
    def chunks(self, text: str) -> list[str]: ...
    def rank(
        self, query: str, rows: list[tuple[Document, DocumentChunk]], limit: int
    ) -> list[tuple[float, Document, DocumentChunk]]: ...


class LocalLexicalIndex:
    def chunks(self, text: str) -> list[str]:
        return chunk_text(text)

    def rank(self, query: str, rows: list[tuple[Document, DocumentChunk]], limit: int):
        query_terms = set(tokens(query))
        counts = [Counter(tokens(chunk.text)) for _, chunk in rows]
        lengths = [sum(count.values()) for count in counts]
        average = sum(lengths) / max(len(lengths), 1) or 1
        frequencies = {term: sum(term in count for count in counts) for term in query_terms}
        ranked = []
        for (document, chunk), count, length in zip(rows, counts, lengths, strict=True):
            score = 0.0
            for term in query_terms:
                tf = count[term]
                idf = math.log(
                    1 + (len(rows) - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
                )
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
            if score > 0:
                ranked.append((score, document, chunk))
        ranked.sort(key=lambda row: (-row[0], str(row[1].id), row[2].position))
        return ranked[:limit]
