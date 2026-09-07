"""Pluggable model and decision-source adapter contracts."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from .models import build_decisions, get_model


@runtime_checkable
class DecisionAdapter(Protocol):
    """Normalize an external model version into auditable decisions."""

    adapter_id: str

    def describe(self) -> dict[str, Any]: ...

    def decisions(self) -> pd.DataFrame: ...


@dataclass(frozen=True)
class ReferenceModelAdapter:
    """Adapter for ChaosHire's deterministic transparent fixtures."""

    model_id: str
    adapter_id: str = "reference-model"

    def describe(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "model_id": self.model_id,
            "mode": "local_scoring",
            "deterministic": True,
        }

    def decisions(self) -> pd.DataFrame:
        return build_decisions(get_model(self.model_id))


@dataclass(frozen=True)
class CallableDecisionAdapter:
    """Safe integration point for an in-process production decision provider."""

    model_id: str
    provider: Callable[[], pd.DataFrame]
    adapter_id: str = "callable-decisions"

    def describe(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "model_id": self.model_id,
            "mode": "provided_decisions",
            "deterministic": False,
        }

    def decisions(self) -> pd.DataFrame:
        frame = self.provider()
        required = {"accepted"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Adapter output is missing required columns: {', '.join(sorted(missing))}.")
        return frame.copy()


def adapter_catalog() -> dict[str, Any]:
    """Document supported integration modes without making unsafe outbound requests."""
    return {
        "contract": "DecisionAdapter.describe() + DecisionAdapter.decisions()",
        "required_normalized_columns": ["accepted"],
        "recommended_columns": ["candidate_id", "qualified", "protected attributes"],
        "adapters": [
            {
                "id": "reference-model",
                "status": "available",
                "use": "Transparent deterministic LegacyCorp and MeritFirst fixtures.",
            },
            {
                "id": "csv-decisions",
                "status": "available",
                "use": "Configurable outcome export through POST /api/upload.",
            },
            {
                "id": "callable-decisions",
                "status": "library",
                "use": "In-process integration for a versioned production decision provider.",
            },
        ],
        "security_note": "ChaosHire consumes decisions; it does not require model weights or execute uploaded code.",
    }
