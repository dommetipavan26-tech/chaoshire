"""Backward-compatible ChaosHire entry point.

Render and existing users can continue running:
    uvicorn backend:app

Application code now lives in the ``chaoshire`` package. Selected names are
re-exported to avoid breaking the v0.1 public API and regression tests.
"""
from chaoshire.app import api_mitigate, app
from chaoshire.config import DECISION_THRESHOLD as THRESHOLD
from chaoshire.config import MIN_CELL_SIZE as MIN_CELL
from chaoshire.data import DEMO_DATA as df
from chaoshire.metrics import attribute_metrics as attr_metrics
from chaoshire.metrics import audit, certificate
from chaoshire.metrics import round4 as f4
from chaoshire.models import (
    BIAS_FEATURES,
    FAIR,
    FEATURE_LABELS,
    LEGACY,
    MODEL_META,
    build_decisions,
    score,
)
from chaoshire.models import (
    FEATURE_DESCRIPTIONS as FEATURE_DESC,
)
from chaoshire.models import (
    feature_components as comps,
)
from chaoshire.schemas import AppealRequest as AppealReq
from chaoshire.schemas import MitigationRequest as MitigateReq
from chaoshire.schemas import UploadRequest as UploadReq
from chaoshire.state import APPEALS, UPLOADED

__all__ = [
    "APPEALS",
    "BIAS_FEATURES",
    "FAIR",
    "FEATURE_DESC",
    "FEATURE_LABELS",
    "LEGACY",
    "MIN_CELL",
    "MODEL_META",
    "THRESHOLD",
    "UPLOADED",
    "AppealReq",
    "MitigateReq",
    "UploadReq",
    "api_mitigate",
    "app",
    "attr_metrics",
    "audit",
    "build_decisions",
    "certificate",
    "comps",
    "df",
    "f4",
    "score",
]
