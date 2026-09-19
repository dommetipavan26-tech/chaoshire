"""FastAPI route layer for ChaosHire."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from . import __version__
from .adapters import adapter_catalog, find_remote_adapter, remote_adapters_from_env
from .agent import review_audit
from .build_info import SERVICE_WORKER_CACHE, build_info
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
from .platform import (
    OPERATIONS,
    WriteAccess,
    platform_middleware,
    require_write_access,
    write_posture,
)
from .quality import compare_models, evaluate_fairness_gate
from .reporting import render_html_report
from .repository import get_audit, initialise_database, list_audits
from .schemas import (
    AgentReviewRequest,
    AppealRequest,
    ChaosRunRequest,
    ConnectorAuditRequest,
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
STATIC_DIR = Path(__file__).resolve().parent / "static"
ICON_FILES = ("icon-192.png", "icon-512.png", "icon-maskable-512.png")
# Constant lookup table: request strings select an entry but never become part
# of a filesystem path, which keeps the icon route free of path-injection taint.
ICON_PATHS: dict[str, Path] = {name: STATIC_DIR / name for name in ICON_FILES}
DATASETS = ("demo", "uploaded")


def require_known_model(
    model: str = Query("legacy", description="Reference model identifier."),
) -> str:
    """Reject unknown model identifiers instead of silently substituting one."""
    if model not in MODEL_META:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown reference model '{model}'. Available models: {', '.join(MODEL_META)}.",
        )
    return model


def require_known_dataset(
    dataset: str = Query(
        "demo", description="'demo' for reference fixtures, 'uploaded' for a CSV audit."
    ),
) -> str:
    if dataset not in DATASETS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown dataset '{dataset}'. Available datasets: {', '.join(DATASETS)}.",
        )
    return dataset


ModelQuery = Annotated[str, Depends(require_known_model)]
DatasetQuery = Annotated[str, Depends(require_known_dataset)]

app = FastAPI(
    title="ChaosHire API",
    version=__version__,
    description=(
        "Fairness auditing, controlled counterfactual stress tests, explanations, "
        "mitigation simulations, and candidate appeals for automated hiring decisions."
    ),
)
app.middleware("http")(platform_middleware)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ChaosHire"}


@app.head("/api/health", include_in_schema=False)
def health_head() -> dict[str, str]:
    return health()


@app.get("/api/live", tags=["system"])
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.head("/api/live", include_in_schema=False)
def liveness_head() -> dict[str, str]:
    return liveness()


@app.get("/api/ready", tags=["system"])
def readiness() -> dict[str, str]:
    try:
        initialise_database()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Audit repository is unavailable.") from error
    return {"status": "ready", "database": "available"}


@app.head("/api/ready", include_in_schema=False)
def readiness_head() -> dict[str, str]:
    return readiness()


@app.get("/api/metrics", tags=["system"])
def operational_metrics() -> dict:
    return OPERATIONS.snapshot()


@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest() -> JSONResponse:
    return JSONResponse(
        {
            "name": "ChaosHire Fairness Auditor",
            "short_name": "ChaosHire",
            "id": "/",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#0b1220",
            "theme_color": "#0b1220",
            "description": "Evidence-grounded chaos testing for hiring-model fairness.",
            "icons": [
                {
                    "src": "/icons/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": "/icons/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": "/icons/icon-maskable-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
        },
        media_type="application/manifest+json",
    )


@app.get("/icons/{name}", include_in_schema=False)
def app_icon(name: str) -> Response:
    icon_path = ICON_PATHS.get(name)
    if icon_path is None:
        raise HTTPException(status_code=404, detail="Icon not found.")
    return Response(
        icon_path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/service-worker.js", include_in_schema=False)
def service_worker() -> Response:
    # The cache name is derived from the package version so a release cannot ship
    # a service worker that keeps serving the previous version's precached shell.
    script = """const CACHE='__CACHE_NAME__';
self.addEventListener('install',e=>e.waitUntil(Promise.all([caches.open(CACHE).then(c=>c.addAll(['/','/manifest.webmanifest','/icons/icon-192.png','/icons/icon-512.png'])),self.skipWaiting()])));
self.addEventListener('activate',e=>e.waitUntil(Promise.all([caches.keys().then(k=>Promise.all(k.filter(x=>x!==CACHE).map(x=>caches.delete(x)))),self.clients.claim()])));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET'||new URL(e.request.url).pathname.startsWith('/api/'))return;e.respondWith(fetch(e.request).then(r=>{const x=r.clone();caches.open(CACHE).then(c=>c.put(e.request,x));return r}).catch(()=>caches.match(e.request)))});""".replace(
        "__CACHE_NAME__", SERVICE_WORKER_CACHE
    )
    return Response(
        script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> HTMLResponse:
    html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
    nonce = getattr(request.state, "csp_nonce", "")
    if nonce:
        # The nonce-based CSP forbids 'unsafe-inline', so the single inline
        # script must carry the per-request nonce.
        html = html.replace("<script>", f'<script nonce="{nonce}">', 1)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})


@app.get("/api/meta", tags=["system"])
def meta() -> dict:
    return {
        "models": list(MODEL_META.values()),
        "feature_labels": FEATURE_LABELS,
        "feature_desc": FEATURE_DESCRIPTIONS,
        "bias_features": BIAS_FEATURES,
        "thresholds": FAIRNESS_THRESHOLDS,
        "sample_ids": ["C-1046", "C-1208", "C-1213", "C-1000", "C-1001"],
        "platform": write_posture(),
        "build": build_info(),
        "schema": (
            "Minimum: one decision column + one group attribute column.\n"
            "Optional: candidate ID and qualification/ground-truth columns. "
            "Column names, favorable values, protected attributes, and minimum group size are configurable."
        ),
    }


@app.get("/api/adapters", tags=["integrations"])
def adapters() -> dict:
    return adapter_catalog()


@app.post(
    "/api/connectors/audit",
    tags=["integrations"],
    dependencies=[Depends(require_write_access)],
)
def audit_remote_connector(request: ConnectorAuditRequest) -> Any:
    """Fetch decisions from an operator-configured remote model and audit them."""
    adapter = find_remote_adapter(request.model_id)
    if adapter is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"No remote connector is configured for '{request.model_id}'.",
                "configured": [configured.model_id for configured in remote_adapters_from_env()],
            },
        )
    try:
        frame = adapter.decisions()
    except Exception as error:
        # Upstream, network, credential, and normalisation failures are a bad
        # gateway, not a ChaosHire server error.
        return JSONResponse(
            status_code=502,
            content={"error": f"Remote model '{request.model_id}' could not be audited: {error}"},
        )
    return {"model_id": request.model_id, "adapter": adapter.describe(), "audit": audit(frame)}


@app.get("/api/demo", tags=["guided demo"])
def demo_story() -> dict:
    return guided_demo()


@app.get("/api/audit", tags=["audit"])
def api_audit(model: ModelQuery, dataset: DatasetQuery) -> Any:
    if dataset == "uploaded":
        result = uploaded_audit()
        if "error" in result:
            return JSONResponse(status_code=404, content=result)
        return result
    return {"model": MODEL_META[model], **audit(build_decisions(get_model(model)))}


@app.get("/api/chaos", tags=["chaos lab"])
def api_chaos(model: ModelQuery) -> dict:
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
def api_filtered(model: ModelQuery) -> dict:
    return filtered_candidates(model)


@app.get("/api/explain/{candidate_id}", tags=["explainability"])
def api_explain(candidate_id: str, model: ModelQuery) -> Any:
    result = explain_candidate(candidate_id, model)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.get("/api/candidate/{candidate_id}", tags=["appeals"])
def api_candidate(candidate_id: str) -> Any:
    result = candidate_decision(candidate_id)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.post("/api/appeals", tags=["appeals"], dependencies=[Depends(require_write_access)])
def post_appeal(request: AppealRequest) -> Any:
    result = create_appeal(request.candidate_id, request.message)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.get("/api/appeals", tags=["appeals"])
def get_appeals() -> dict:
    return list_appeals()


@app.post("/api/mitigate", tags=["mitigation"])
def api_mitigate(request: MitigationRequest) -> Any:
    result = mitigate(
        list(request.strategies),
        threshold_contrast_acknowledged=request.threshold_contrast_acknowledged,
    )
    if "error" in result:
        return JSONResponse(status_code=422, content=result)
    return result


@app.post("/api/upload", tags=["audit"])
def api_upload(
    request: UploadRequest,
    access: Annotated[WriteAccess, Depends(require_write_access)],
) -> Any:
    # Only an authenticated operator may publish an audit to the shared slot and
    # the persistent history that every visitor reads. Anonymous uploads are
    # computed and returned inline, then discarded.
    result = upload_decisions(
        csv_text=request.csv,
        audit_name=request.audit_name,
        decision_column=request.decision_column,
        favorable_values=request.favorable_values,
        qualification_column=request.qualification_column,
        qualified_values=request.qualified_values,
        protected_attributes=request.protected_attributes,
        candidate_id_column=request.candidate_id_column,
        minimum_group_size=request.minimum_group_size,
        publish=access.authenticated,
    )
    if "error" in result:
        return JSONResponse(status_code=422, content=result)
    return result


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
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return JSONResponse(
        content=result,
        headers={"Content-Disposition": "attachment; filename=chaoshire-audit.json"},
    )


def _report_inputs(model: ModelQuery, dataset: DatasetQuery) -> tuple[dict, dict | None]:
    """Resolve report inputs; both identifiers are validated by the route layer."""
    if dataset == "uploaded":
        result = uploaded_audit()
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result, None
    return audit(build_decisions(get_model(model))), run_chaos_suite(model, evidence_limit=0)


@app.post("/api/agent/review", tags=["fairness agent"])
def agent_review(request: AgentReviewRequest) -> dict:
    result, chaos_result = _report_inputs(request.model, request.dataset)
    return review_audit(result, chaos_result if request.include_chaos else None)


@app.get("/api/evidence", tags=["evidence"])
def evidence_bundle(model: ModelQuery, dataset: DatasetQuery) -> dict:
    result, chaos_result = _report_inputs(model, dataset)
    review = review_audit(result, chaos_result)
    return build_evidence_bundle(result, chaos_result, review)


@app.post("/api/evidence/verify", tags=["evidence"])
def verify_evidence(request: EvidenceVerifyRequest) -> dict:
    return verify_evidence_bundle(request.bundle)


@app.get("/api/report.html", response_class=HTMLResponse, tags=["reports"])
def html_report(model: ModelQuery, dataset: DatasetQuery) -> HTMLResponse:
    result, chaos_result = _report_inputs(model, dataset)
    return HTMLResponse(
        render_html_report(result, chaos_result),
        headers={"Content-Disposition": "attachment; filename=chaoshire-report.html"},
    )


@app.get("/api/report.pdf", tags=["reports"])
def pdf_report(model: ModelQuery, dataset: DatasetQuery) -> Response:
    result, chaos_result = _report_inputs(model, dataset)
    return Response(
        render_pdf_report(result, chaos_result),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=chaoshire-report.pdf"},
    )


@app.get("/api/sample.csv", response_class=PlainTextResponse, tags=["audit"])
def get_sample_csv() -> str:
    return sample_csv()
