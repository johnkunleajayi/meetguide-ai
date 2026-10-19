from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    speaker: Literal["them", "you"]
    text: str = Field(min_length=1, max_length=1000, repr=False)


class CueInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    type: Literal["question"]
    speaker: Literal["them"]
    finalized: Literal[True]
    confidence: float = Field(ge=0.82, le=1, allow_inf_nan=False)
    question: str = Field(min_length=8, max_length=1600, repr=False)
    context: list[Turn] = Field(default_factory=list, max_length=6, repr=False)

    @model_validator(mode="after")
    def bounded_context(self):
        if sum(len(turn.text) for turn in self.context) > 4000:
            raise ValueError("Conversation context is too long")
        return self


class Evidence(BaseModel):
    id: str
    document_id: UUID
    chunk_id: UUID
    text: str = Field(repr=False)


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    paragraphs: list[str] = Field(min_length=2, max_length=3, repr=False)
    evidence_ids: list[str] = Field(default_factory=list, max_length=3)


class SourceReference(BaseModel):
    document_id: UUID
    chunk_id: UUID


class CueResult(BaseModel):
    answer: str = Field(repr=False)
    grounding: Literal["document_supported", "general_approach"]
    sources: list[SourceReference]
