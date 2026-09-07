"""Pydantic request models for the public API."""
from pydantic import BaseModel, Field


class AppealRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=5000)


class MitigationRequest(BaseModel):
    strategies: list[str]


class VerdictThreshold(BaseModel):
    warn: float = Field(ge=0, le=1)
    fail: float = Field(ge=0, le=1)


class ChaosRunRequest(BaseModel):
    model: str = Field(default="legacy", pattern="^(legacy|fair)$")
    thresholds: dict[str, VerdictThreshold] | None = None
    evidence_limit: int = Field(default=10, ge=0, le=50)


class FairnessGateRequest(BaseModel):
    baseline_model: str = Field(default="legacy", pattern="^(legacy|fair)$")
    candidate_model: str = Field(default="fair", pattern="^(legacy|fair)$")
    minimum_certificate: int = Field(default=75, ge=0, le=100)
    minimum_resilience: int = Field(default=80, ge=0, le=100)
    minimum_disparate_impact: float = Field(default=0.8, ge=0, le=1)
    maximum_certificate_regression: int = Field(default=0, ge=0, le=100)
    maximum_resilience_regression: int = Field(default=0, ge=0, le=100)


class AgentReviewRequest(BaseModel):
    model: str = Field(default="legacy", pattern="^(legacy|fair)$")
    dataset: str = Field(default="demo", pattern="^(demo|uploaded)$")
    include_chaos: bool = True


class EvidenceVerifyRequest(BaseModel):
    bundle: dict


class UploadRequest(BaseModel):
    """Configuration for interpreting a model-decision CSV export."""

    csv: str = Field(min_length=1, max_length=5_000_000)
    audit_name: str = Field(default="Untitled CSV audit", min_length=1, max_length=100)
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
