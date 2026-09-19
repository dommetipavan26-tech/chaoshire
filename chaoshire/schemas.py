"""Pydantic request models for the public API."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AppealRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=5000)


# Must stay in sync with ``chaoshire.services.MITIGATION_STRATEGIES``.
# Per-group threshold calibration is deliberately absent: 42 U.S.C. § 2000e-2(l)
# makes different cutoff scores by protected group unlawful in US employment
# testing. It survives only as the opt-in research contrast below.
MitigationStrategy = Literal["blind", "proxy"]


class MitigationRequest(BaseModel):
    strategies: list[MitigationStrategy] = Field(default_factory=list, max_length=2)
    threshold_contrast_acknowledged: bool | None = Field(
        default=None,
        description=(
            "Tri-state opt-in for the research-only per-group threshold contrast. "
            "Omit to skip it; send true to run it. Per-group cutoff scores are "
            "unlawful in US employment testing under 42 U.S.C. § 2000e-2(l), so the "
            "result is reported separately as a contrast and never as a remediation."
        ),
    )

    @model_validator(mode="after")
    def _require_a_control(self) -> "MitigationRequest":
        if not self.strategies and self.threshold_contrast_acknowledged is None:
            raise ValueError(
                "Select at least one mitigation strategy, or request the research-only "
                "threshold contrast explicitly."
            )
        return self


class VerdictThreshold(BaseModel):
    warn: float = Field(ge=0, le=1)
    fail: float = Field(ge=0, le=1)


class ChaosRunRequest(BaseModel):
    model: str = Field(default="legacy", pattern="^(legacy|fair|trained)$")
    thresholds: dict[str, VerdictThreshold] | None = None
    evidence_limit: int = Field(default=10, ge=0, le=50)


class FairnessGateRequest(BaseModel):
    baseline_model: str = Field(default="legacy", pattern="^(legacy|fair|trained)$")
    candidate_model: str = Field(default="fair", pattern="^(legacy|fair|trained)$")
    minimum_certificate: int = Field(default=75, ge=0, le=100)
    minimum_resilience: int = Field(default=80, ge=0, le=100)
    minimum_disparate_impact: float = Field(default=0.8, ge=0, le=1)
    maximum_certificate_regression: int = Field(default=0, ge=0, le=100)
    maximum_resilience_regression: int = Field(default=0, ge=0, le=100)


class AgentReviewRequest(BaseModel):
    model: str = Field(default="legacy", pattern="^(legacy|fair|trained)$")
    dataset: str = Field(default="demo", pattern="^(demo|uploaded)$")
    include_chaos: bool = True


class EvidenceVerifyRequest(BaseModel):
    bundle: dict


class ConnectorAuditRequest(BaseModel):
    """Selects an operator-configured remote decision source by identifier."""

    model_id: str = Field(min_length=1, max_length=100)


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
