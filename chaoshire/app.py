"""FastAPI route layer for ChaosHire."""
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from . import __version__
from .adapters import adapter_catalog
from .agent import review_audit
from .chaos import run_chaos_suite
from .config import FAIRNESS_THRESHOLDS
from .demo import guided_demo
from .evidence import build_evidence_bundle, verify_evidence_bundle
from .metrics import audit
from .models import (
    BIAS_FEATURES,
    FEATURE_DESCRIPTIONS,
    FEATURE_LABELS,
    MODEL_META,
    build_decisions,
    get_model,
)
from .pdf_reporting import render_pdf_report
from .platform import OPERATIONS, platform_middleware, require_write_access
from .quality import compare_models, evaluate_fairness_gate
from .reporting import render_html_report
from .repository import get_audit, initialise_database, list_audits
from .schemas import (
    AgentReviewRequest,
    AppealRequest,
    ChaosRunRequest,
    EvidenceVerifyRequest,
    FairnessGateRequest,
    MitigationRequest,
    UploadRequest,
)
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
app.middleware("http")(platform_middleware)


@app.api_route("/api/health", methods=["GET", "HEAD"], tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ChaosHire"}


@app.api_route("/api/live", methods=["GET", "HEAD"], tags=["system"])
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.api_route("/api/ready", methods=["GET", "HEAD"], tags=["system"])
def readiness() -> dict[str, str]:
    try:
        initialise_database()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Audit repository is unavailable.") from error
    return {"status": "ready", "database": "available"}


@app.get("/api/metrics", tags=["system"])
def operational_metrics() -> dict:
    return OPERATIONS.snapshot()


@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest() -> JSONResponse:
    return JSONResponse(
        {
            "name": "ChaosHire Fairness Auditor",
            "short_name": "ChaosHire",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0b1220",
            "theme_color": "#0b1220",
            "description": "Evidence-grounded chaos testing for hiring-model fairness.",
        },
        media_type="application/manifest+json",
    )


@app.get("/service-worker.js", include_in_schema=False)
def service_worker() -> Response:
    script = """const CACHE='chaoshire-v0211';
self.addEventListener('install',e=>e.waitUntil(Promise.all([caches.open(CACHE).then(c=>c.addAll(['/','/manifest.webmanifest'])),self.skipWaiting()])));
self.addEventListener('activate',e=>e.waitUntil(Promise.all([caches.keys().then(k=>Promise.all(k.filter(x=>x!==CACHE).map(x=>caches.delete(x)))),self.clients.claim()])));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET'||new URL(e.request.url).pathname.startsWith('/api/'))return;e.respondWith(fetch(e.request).then(r=>{const x=r.clone();caches.open(CACHE).then(c=>c.put(e.request,x));return r}).catch(()=>caches.match(e.request)))});"""
    return Response(
        script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> HTMLResponse:
    return HTMLResponse(
        content=(PROJECT_ROOT / "index.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache"},
    )


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


@app.get("/api/adapters", tags=["integrations"])
def adapters() -> dict:
    return adapter_catalog()


@app.get("/api/demo", tags=["guided demo"])
def demo_story() -> dict:
    return guided_demo()


@app.get("/api/audit", tags=["audit"])
def api_audit(model: str = "legacy", dataset: str = "demo") -> dict:
    if dataset == "uploaded":
        return uploaded_audit()
    return audit(build_decisions(get_model(model)))


@app.get("/api/chaos", tags=["chaos lab"])
def api_chaos(model: str = "legacy") -> dict:
    return run_chaos_suite(model)


@app.post("/api/chaos/run", tags=["chaos lab"])
def configured_chaos_run(request: ChaosRunRequest) -> dict:
    thresholds = (
        {test_id: values.model_dump() for test_id, values in request.thresholds.items()}
        if request.thresholds
        else None
    )
    try:
        return run_chaos_suite(request.model, thresholds, request.evidence_limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/compare", tags=["continuous fairness"])
def model_comparison(baseline: str = "legacy", candidate: str = "fair") -> dict:
    if baseline not in MODEL_META or candidate not in MODEL_META:
        raise HTTPException(status_code=400, detail="Unknown reference model.")
    return compare_models(baseline, candidate)


@app.post("/api/gate", tags=["continuous fairness"])
def fairness_gate(request: FairnessGateRequest) -> dict:
    return evaluate_fairness_gate(**request.model_dump())


@app.get("/api/filtered", tags=["explainability"])
def api_filtered(model: str = "legacy") -> dict:
    return filtered_candidates(model)


@app.get("/api/explain/{candidate_id}", tags=["explainability"])
def api_explain(candidate_id: str, model: str = "legacy") -> dict:
    return explain_candidate(candidate_id, model)


@app.get("/api/candidate/{candidate_id}", tags=["appeals"])
def api_candidate(candidate_id: str) -> dict:
    return candidate_decision(candidate_id)


@app.post("/api/appeals", tags=["appeals"], dependencies=[Depends(require_write_access)])
def post_appeal(request: AppealRequest) -> dict:
    return create_appeal(request.candidate_id, request.message)


@app.get("/api/appeals", tags=["appeals"])
def get_appeals() -> dict:
    return list_appeals()


@app.post("/api/mitigate", tags=["mitigation"])
def api_mitigate(request: MitigationRequest) -> dict:
    return mitigate(request.strategies)


@app.post("/api/upload", tags=["audit"], dependencies=[Depends(require_write_access)])
def api_upload(request: UploadRequest) -> dict:
    return upload_decisions(
        csv_text=request.csv,
        audit_name=request.audit_name,
        decision_column=request.decision_column,
        favorable_values=request.favorable_values,
        qualification_column=request.qualification_column,
        qualified_values=request.qualified_values,
        protected_attributes=request.protected_attributes,
        candidate_id_column=request.candidate_id_column,
        minimum_group_size=request.minimum_group_size,
    )


@app.get("/api/audits", tags=["audit history"])
def audit_history(limit: int = 50) -> dict:
    return {"audits": list_audits(limit)}


@app.get("/api/audits/{audit_id}", tags=["audit history"])
def audit_detail(audit_id: str) -> dict:
    result = get_audit(audit_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Audit record not found.")
    return result


@app.get("/api/audit/export", response_class=JSONResponse, tags=["audit"])
def export_uploaded_audit() -> JSONResponse:
    result = uploaded_audit()
    return JSONResponse(
        content=result,
        headers={"Content-Disposition": "attachment; filename=chaoshire-audit.json"},
    )


def _report_inputs(model: str, dataset: str) -> tuple[dict, dict | None]:
    if dataset == "uploaded":
        result = uploaded_audit()
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result, None
    if model not in MODEL_META:
        raise HTTPException(status_code=400, detail="Unknown reference model.")
    return audit(build_decisions(get_model(model))), run_chaos_suite(model, evidence_limit=0)


@app.post("/api/agent/review", tags=["fairness agent"])
def agent_review(request: AgentReviewRequest) -> dict:
    result, chaos_result = _report_inputs(request.model, request.dataset)
    return review_audit(result, chaos_result if request.include_chaos else None)


@app.get("/api/evidence", tags=["evidence"])
def evidence_bundle(model: str = "legacy", dataset: str = "demo") -> dict:
    result, chaos_result = _report_inputs(model, dataset)
    review = review_audit(result, chaos_result)
    return build_evidence_bundle(result, chaos_result, review)


@app.post("/api/evidence/verify", tags=["evidence"])
def verify_evidence(request: EvidenceVerifyRequest) -> dict:
    return verify_evidence_bundle(request.bundle)


@app.get("/api/report.html", response_class=HTMLResponse, tags=["reports"])
def html_report(model: str = "legacy", dataset: str = "demo") -> HTMLResponse:
    result, chaos_result = _report_inputs(model, dataset)
    return HTMLResponse(
        render_html_report(result, chaos_result),
        headers={"Content-Disposition": "attachment; filename=chaoshire-report.html"},
    )


@app.get("/api/report.pdf", tags=["reports"])
def pdf_report(model: str = "legacy", dataset: str = "demo") -> Response:
    result, chaos_result = _report_inputs(model, dataset)
    return Response(
        render_pdf_report(result, chaos_result),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=chaoshire-report.pdf"},
    )


@app.get("/api/sample.csv", response_class=PlainTextResponse, tags=["audit"])
def get_sample_csv() -> str:
    return sample_csv()
