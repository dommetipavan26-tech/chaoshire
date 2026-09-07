"""FastAPI route layer for ChaosHire."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from . import __version__
from .chaos import run_chaos_suite
from .config import FAIRNESS_THRESHOLDS
from .metrics import audit
from .models import (
    BIAS_FEATURES,
    FEATURE_DESCRIPTIONS,
    FEATURE_LABELS,
    MODEL_META,
    build_decisions,
    get_model,
)
from .schemas import AppealRequest, MitigationRequest, UploadRequest
from .services import (
    candidate_decision,
    create_appeal,
    explain_candidate,
    filtered_candidates,
    list_appeals,
    mitigate,
    sample_csv,
    upload_decisions,
    uploaded_audit,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="ChaosHire API",
    version=__version__,
    description=(
        "Fairness auditing, controlled counterfactual stress tests, explanations, "
        "mitigation simulations, and candidate appeals for automated hiring decisions."
    ),
)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ChaosHire"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> str:
    return (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")


@app.get("/api/meta", tags=["system"])
def meta() -> dict:
    return {
        "models": list(MODEL_META.values()),
        "feature_labels": FEATURE_LABELS,
        "feature_desc": FEATURE_DESCRIPTIONS,
        "bias_features": BIAS_FEATURES,
        "thresholds": FAIRNESS_THRESHOLDS,
        "sample_ids": ["C-1046", "C-1208", "C-1213", "C-1000", "C-1001"],
        "schema": (
            "Minimum: one decision column + one group attribute column.\n"
            "Optional: candidate ID and qualification/ground-truth columns. "
            "Column names, favorable values, protected attributes, and minimum group size are configurable."
        ),
    }


@app.get("/api/audit", tags=["audit"])
def api_audit(model: str = "legacy", dataset: str = "demo") -> dict:
    if dataset == "uploaded":
        return uploaded_audit()
    return audit(build_decisions(get_model(model)))


@app.get("/api/chaos", tags=["chaos lab"])
def api_chaos(model: str = "legacy") -> dict:
    return run_chaos_suite(model)


@app.get("/api/filtered", tags=["explainability"])
def api_filtered(model: str = "legacy") -> dict:
    return filtered_candidates(model)


@app.get("/api/explain/{candidate_id}", tags=["explainability"])
def api_explain(candidate_id: str, model: str = "legacy") -> dict:
    return explain_candidate(candidate_id, model)


@app.get("/api/candidate/{candidate_id}", tags=["appeals"])
def api_candidate(candidate_id: str) -> dict:
    return candidate_decision(candidate_id)


@app.post("/api/appeals", tags=["appeals"])
def post_appeal(request: AppealRequest) -> dict:
    return create_appeal(request.candidate_id, request.message)


@app.get("/api/appeals", tags=["appeals"])
def get_appeals() -> dict:
    return list_appeals()


@app.post("/api/mitigate", tags=["mitigation"])
def api_mitigate(request: MitigationRequest) -> dict:
    return mitigate(request.strategies)


@app.post("/api/upload", tags=["audit"])
def api_upload(request: UploadRequest) -> dict:
    return upload_decisions(
        csv_text=request.csv,
        decision_column=request.decision_column,
        favorable_values=request.favorable_values,
        qualification_column=request.qualification_column,
        qualified_values=request.qualified_values,
        protected_attributes=request.protected_attributes,
        candidate_id_column=request.candidate_id_column,
        minimum_group_size=request.minimum_group_size,
    )


@app.get("/api/audit/export", response_class=JSONResponse, tags=["audit"])
def export_uploaded_audit() -> JSONResponse:
    result = uploaded_audit()
    return JSONResponse(
        content=result,
        headers={"Content-Disposition": "attachment; filename=chaoshire-audit.json"},
    )


@app.get("/api/sample.csv", response_class=PlainTextResponse, tags=["audit"])
def get_sample_csv() -> str:
    return sample_csv()
