from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cues.domain import Turn


class IntentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    text: str = Field(min_length=1, max_length=1600, repr=False)
    context: list[Turn] = Field(default_factory=list, max_length=6, repr=False)
    previous_request: str | None = Field(default=None, max_length=1600, repr=False)
    can_continue: bool = False

    @model_validator(mode="after")
    def bounded(self):
        if sum(len(turn.text) for turn in self.context) > 4000:
            raise ValueError("Conversation context is too long")
        if self.can_continue and not self.previous_request:
            raise ValueError("Continuation requires a previous request")
        return self


class IntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    kind: Literal["ACTIONABLE_REQUEST", "CONTINUATION", "FOLLOW_UP", "NOT_ACTIONABLE"]
    normalized_request: str = Field(max_length=1600, repr=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def complete(self):
        if self.kind != "NOT_ACTIONABLE" and len(self.normalized_request.strip()) < 4:
            raise ValueError("An actionable intent requires a request")
        return self
