from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from app.preparations.domain import PreparedContext


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    speaker: Literal["them", "you"]
    text: str = Field(min_length=1, max_length=1000, repr=False)


class CodingContext(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    problem: str = Field(min_length=1, max_length=1600, repr=False)
    language: str = Field(default="auto", max_length=40)
    code: str = Field(default="", max_length=8000, repr=False)


class CueInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    cue_kind: Literal["conversation", "code"] = "conversation"
    coding_context: CodingContext | None = Field(default=None, repr=False)
    preparation_token: str | None = Field(default=None, max_length=12000, repr=False)
    _preparation: PreparedContext | None = PrivateAttr(default=None)
    type: Literal["question"]
    speaker: Literal["them"]
    finalized: Literal[True]
    confidence: float = Field(ge=0.82, le=1, allow_inf_nan=False)
    question: str = Field(min_length=4, max_length=1600, repr=False)
    context: list[Turn] = Field(default_factory=list, max_length=6, repr=False)

    @model_validator(mode="after")
    def bounded_context(self):
        if len(self.question) < 8 and not self.context:
            raise ValueError("A short follow-up requires recent conversation context")
        if sum(len(turn.text) for turn in self.context) > 4000:
            raise ValueError("Conversation context is too long")
        return self


class Evidence(BaseModel):
    context_role: str = "other"
    id: str
    document_id: UUID
    chunk_id: UUID
    text: str = Field(repr=False)


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    paragraphs: list[str] = Field(min_length=2, max_length=3, repr=False)
    evidence_ids: list[str] = Field(default_factory=list, max_length=3)


class CodeAssist(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    language: str = Field(min_length=1, max_length=40)
    approach: str = Field(min_length=1, max_length=1600, repr=False)
    code: str = Field(min_length=1, max_length=8000, repr=False)
    complexity: str | None = Field(default=None, max_length=1000)
    what_to_say: str = Field(min_length=1, max_length=1800, repr=False)


class CodeDraft(CodeAssist):
    evidence_ids: list[str] = Field(default_factory=list, max_length=3)


class SourceReference(BaseModel):
    document_id: UUID
    chunk_id: UUID


class CueResult(BaseModel):
    code_assist: CodeAssist | None = None
    answer: str = Field(repr=False)
    grounding: Literal["document_supported", "general_approach"]
    sources: list[SourceReference]
