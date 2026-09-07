"""Pydantic request models for the public API."""
from pydantic import BaseModel, Field


class AppealRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=5000)


class MitigationRequest(BaseModel):
    strategies: list[str]


class UploadRequest(BaseModel):
    """Configuration for interpreting a model-decision CSV export."""

    csv: str = Field(min_length=1, max_length=5_000_000)
    decision_column: str = Field(default="decision", min_length=1, max_length=100)
    favorable_values: list[str] = Field(
        default_factory=lambda: ["1", "true", "yes", "y", "accept", "accepted"],
        min_length=1,
        max_length=20,
    )
    qualification_column: str | None = Field(default=None, max_length=100)
    qualified_values: list[str] = Field(
        default_factory=lambda: ["1", "true", "yes", "y"],
        min_length=1,
        max_length=20,
    )
    protected_attributes: list[str] | None = Field(default=None, max_length=10)
    candidate_id_column: str | None = Field(default="candidate_id", max_length=100)
    minimum_group_size: int = Field(default=30, ge=2, le=500)
