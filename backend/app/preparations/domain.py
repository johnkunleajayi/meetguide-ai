"""Extensible identifiers; listed purposes/categories are guidance, not engine branches."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PURPOSES = {
    "job_interview": "Job Interview",
    "sales_meeting": "Sales Meeting",
    "client_meeting": "Client Meeting",
    "internal_meeting": "Internal Meeting",
    "presentation": "Presentation / Q&A",
    "custom": "Custom",
}
CATEGORIES = {
    "resume",
    "job_description",
    "company_profile",
    "client_profile",
    "product_information",
    "proposal",
    "agenda",
    "project_document",
    "meeting_notes",
    "presentation",
    "reference_material",
    "other",
}
IDENTIFIER = r"^[a-z][a-z0-9_]{0,63}$"


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    document_id: UUID
    context_role: str = Field(default="other", pattern=IDENTIFIER)


class PreparationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    purpose: str = Field(pattern=IDENTIFIER)
    objective: str = Field(min_length=1, max_length=600, repr=False)
    documents: list[Selection] = Field(default_factory=list, max_length=50)


class PreparedContext(PreparationInput):
    preparation_id: UUID
    user_id: UUID


class PreparationView(PreparationInput):
    id: UUID
    created_at: datetime
    updated_at: datetime
    active: bool = False
