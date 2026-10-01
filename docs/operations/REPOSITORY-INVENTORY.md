# Repository file inventory

Every tracked/non-ignored new source file is listed below with its responsibility and structural checks.
PASS here means those checks passed; it does **not** certify runtime behavior or production security.
See [the dated repository audit](REPOSITORY-AUDIT.md) for executed tests, findings and next updates.

Regenerate from the repository root with:

```bash
python scripts/check_repository.py --require-node --inventory docs/operations/REPOSITORY-INVENTORY.md
```

Files checked: **150**.

## Application

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `chaoshire/__init__.py` | ChaosHire fairness-auditing package. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/__main__.py` | Run ChaosHire command-line tools with ``python -m chaoshire``. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/adapters.py` | Pluggable model and decision-source adapter contracts. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/agent.py` | Deterministic, evidence-grounded fairness review. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/app.py` | FastAPI route layer for ChaosHire. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/build_info.py` | Single source of truth for the build facts the landing page and README quote. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/chaos.py` | Reusable controlled-experiment framework for hiring-model chaos tests. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/cli.py` | Command-line tools for CI/CD fairness gates and report generation. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/config.py` | Shared application configuration and audit thresholds. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/data.py` | Deterministic synthetic data used by the public demonstration. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/decisions.py` | One strict boundary for decision labels consumed by adapters and fairness metrics. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/demo.py` | Stable guided demonstration story for reviewers and interviews. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/evidence.py` | Tamper-evident aggregate evidence bundles. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/explain.py` | SHAP-compatible explanation adapter for linear decision models. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/loghook.py` | Best-effort aggregate log delivery with bounded workers, bytes, and outstanding jobs. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/metrics.py` | Group-fairness metrics and the transparent fairness risk-score calculation. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/models.py` | Reference scoring models and feature transformations. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/pdf_reporting.py` | Dependency-free native PDF summary renderer. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/platform.py` | Security, access-control, and lightweight operational primitives. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/quality.py` | Model comparison and automated fairness release gates. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/redaction.py` | Read-path redaction for the public appeal queue. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/reporting.py` | Self-contained HTML audit report generation. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/repository.py` | Repository dispatcher and SQLite backend for aggregate audit evidence. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/repository_postgres.py` | Optional PostgreSQL repository adapter for durable cloud history. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/schemas.py` | Pydantic request models for the public API. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/services.py` | Application services shared by the HTTP route layer. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/site.py` | Public site metadata and small, first-party, consent-based traffic counters. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/state.py` | Bounded in-memory demo state. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `chaoshire/training.py` | Build-time trainer for the bundled ``trained`` reference model. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Automation

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `.github/dependabot.yml` | Scheduled Python and GitHub Actions dependency updates | UTF-8/nonempty; limited secret-signature scan; YAML parse/unique keys | PASS |
| `.github/workflows/browser.yml` | Browser GitHub Actions workflow | UTF-8/nonempty; limited secret-signature scan; immutable external Action refs; YAML parse/unique keys | PASS |
| `.github/workflows/fairness-gate.yml` | Fairness Gate GitHub Actions workflow | UTF-8/nonempty; limited secret-signature scan; immutable external Action refs; YAML parse/unique keys | PASS |
| `.github/workflows/live-site.yml` | Live Site GitHub Actions workflow | UTF-8/nonempty; limited secret-signature scan; immutable external Action refs; YAML parse/unique keys | PASS |
| `.github/workflows/release.yml` | Release GitHub Actions workflow | UTF-8/nonempty; limited secret-signature scan; immutable external Action refs; YAML parse/unique keys | PASS |
| `.github/workflows/security.yml` | Security GitHub Actions workflow | UTF-8/nonempty; limited secret-signature scan; immutable external Action refs; YAML parse/unique keys | PASS |
| `.github/workflows/test.yml` | Test GitHub Actions workflow | UTF-8/nonempty; limited secret-signature scan; immutable external Action refs; YAML parse/unique keys | PASS |

## Dependency constraints

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `constraints/requirements-py311.txt` | Dependency manifest: py311 | UTF-8/nonempty; limited secret-signature scan; requirement syntax/includes | PASS |
| `constraints/requirements-py312.txt` | Dependency manifest: py312 | UTF-8/nonempty; limited secret-signature scan; requirement syntax/includes | PASS |

## Documentation: engineering

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `docs/engineering/ARCHITECTURE.svg` | ARCHITECTURE.svg | UTF-8/nonempty; limited secret-signature scan; SVG XML parse | PASS |
| `docs/engineering/CONTINUOUS-FAIRNESS.md` | Continuous fairness engineering | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/engineering/METHODOLOGY.md` | ChaosHire statistical methodology | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/engineering/REAL-DATA-AUDIT.md` | Real-data audit: UCI Adult (Census Income) | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/engineering/SCIKIT-LEARN-INTEGRATION.md` | scikit-learn decision-adapter example | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |

## Documentation: index

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `docs/README.md` | ChaosHire documentation | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |

## Documentation: operations

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `docs/operations/MONITORING.md` | Free deployment monitoring | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/operations/PERSISTENCE.md` | Audit-history persistence and privacy | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/operations/RELEASE-CHECKLIST.md` | Release checklist | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/operations/REPOSITORY-AUDIT.md` | Repository audit and completed updates — 1 October 2026 | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/operations/REPOSITORY-INVENTORY.md` | Repository file inventory | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/operations/WEBSITE-READINESS.md` | Website readiness and page-speed check | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |

## Documentation: planning

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `docs/planning/PROJECT-ROADMAP.md` | ChaosHire development roadmap | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/planning/TODO.md` | ChaosHire portfolio backlog | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |

## Documentation: portfolio

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `docs/portfolio/PORTFOLIO-CASE-STUDY.md` | ChaosHire — portfolio case study | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/portfolio/PORTFOLIO-EVIDENCE.md` | ChaosHire portfolio evidence | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/portfolio/PORTFOLIO-PLATFORM.md` | Portfolio platform engineering (Days 11–20) | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `docs/portfolio/assets/dashboard-desktop.png` | Portfolio screenshot | PNG chunks/CRC/dimensions | PASS |
| `docs/portfolio/assets/landing-desktop.png` | Portfolio screenshot | PNG chunks/CRC/dimensions | PASS |
| `docs/portfolio/assets/landing-mobile.png` | Portfolio screenshot | PNG chunks/CRC/dimensions | PASS |
| `docs/portfolio/assets/redesign-after-desktop.png` | Portfolio screenshot | PNG chunks/CRC/dimensions | PASS |
| `docs/portfolio/assets/redesign-after-mobile.png` | Portfolio screenshot | PNG chunks/CRC/dimensions | PASS |
| `docs/portfolio/assets/redesign-before-desktop.png` | Portfolio screenshot | PNG chunks/CRC/dimensions | PASS |
| `docs/portfolio/assets/redesign-before-mobile.png` | Portfolio screenshot | PNG chunks/CRC/dimensions | PASS |

## Integration examples

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `examples/adult_income_audit.py` | Audit real-world predictions: the UCI Adult (Census Income) benchmark. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `examples/sklearn_decision_adapter.py` | Audit reproducible scikit-learn predictions through ChaosHire&#x27;s adapter contract. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Maintenance scripts

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `scripts/capture_portfolio.py` | Capture deterministic portfolio screenshots from a running ChaosHire app. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/capture_redesign.py` | Capture deterministic before/after redesign screenshots from a running app. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/check_accessibility.py` | Audit rendered pages with locally supplied axe-core and Playwright Chromium. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/check_build_info.py` | Fail the build when the committed build facts stop matching reality. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/check_distribution.py` | Verify distribution metadata/data and smoke a fresh runtime-only wheel installation. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/check_live_site.py` | Check a deployed ChaosHire site from the outside. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/check_page_speed.py` | Measure real-browser local load timings without inventing a Lighthouse score. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/check_repository.py` | Check every version-controlled/new source file without importing application code. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/compile_constraints.py` | Resolve reviewable Linux/CPython constraints, including the isolated build backend. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/generate_icons.py` | Generate the deterministic ChaosHire PWA icon set. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/generate_social_preview.py` | Draw the lightweight 1200×630 social sharing card without external assets. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `scripts/probe_xff.py` | Prove the live left-most X-Forwarded-For rate-limit rule (plus instance cap). | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Model artifact

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `chaoshire/artifacts/trained_model.json` | trained model.json | UTF-8/nonempty; limited secret-signature scan; strict JSON; model coefficient digest | PASS |

## Root configuration and community

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `.dockerignore` | Keep local state and development assets out of the image | UTF-8/nonempty; limited secret-signature scan | PASS |
| `.env.example` | Documented environment defaults; no real credentials | UTF-8/nonempty; limited secret-signature scan | PASS |
| `.gitignore` | Keep local secrets, state and generated output out of Git | UTF-8/nonempty; limited secret-signature scan | PASS |
| `CHANGELOG.md` | Changelog | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `CONTRIBUTING.md` | Contributing to ChaosHire | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `Dockerfile` | Non-root runtime container and readiness check | UTF-8/nonempty; limited secret-signature scan | PASS |
| `LICENSE` | Project MIT license | UTF-8/nonempty; limited secret-signature scan | PASS |
| `README.md` | ChaosHire | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `SECURITY.md` | Security and data safety | UTF-8/nonempty; limited secret-signature scan; relative Markdown links/headings | PASS |
| `backend.py` | Backward-compatible ChaosHire entry point. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `pyproject.toml` | Package metadata and Python quality-tool configuration | UTF-8/nonempty; limited secret-signature scan; TOML parse | PASS |
| `render.yaml` | Render deployment Blueprint (not live deployment evidence) | UTF-8/nonempty; limited secret-signature scan; YAML parse/unique keys | PASS |
| `requirements-browser.txt` | Dependency manifest: browser | UTF-8/nonempty; limited secret-signature scan; requirement syntax/includes | PASS |
| `requirements-dev.txt` | Dependency manifest: dev | UTF-8/nonempty; limited secret-signature scan; requirement syntax/includes | PASS |
| `requirements-examples.txt` | Dependency manifest: examples | UTF-8/nonempty; limited secret-signature scan; requirement syntax/includes | PASS |
| `requirements-maintenance.txt` | Dependency manifest: maintenance | UTF-8/nonempty; limited secret-signature scan; requirement syntax/includes | PASS |
| `requirements-postgres.txt` | Dependency manifest: postgres | UTF-8/nonempty; limited secret-signature scan; requirement syntax/includes | PASS |
| `requirements.txt` | Runtime dependency manifest | UTF-8/nonempty; limited secret-signature scan; requirement syntax/includes | PASS |

## Tests: api

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `tests/api/test_api.py` | Public API contract tests. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/api/test_appeals_redaction.py` | `GET /api/appeals` serves redacted copies, never the raw queue. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/api/test_configurable_upload.py` | Tests for configurable bring-your-own-model audits. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/api/test_request_safety.py` | Regression tests for request/evidence edge cases found in the repository audit. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/api/test_shap_adapter.py` | Tests for the SHAP-compatible explanation adapter (chaoshire.explain). | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/api/test_status_contract.py` | HTTP semantics for business failures (v0.23.0 status contract). | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/api/test_verification_fixes.py` | Regression tests for the 2026-09-13 verification findings. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/api/test_write_access.py` | Fix #4 — write access, rate limits, and the bounded appeal queue. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Tests: browser

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `tests/browser/conftest.py` | The real-browser suite uses the app&#x27;s default demo configuration. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/browser/test_landing.py` | Real-browser checks for the recruiter landing experience. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/browser/test_layout.py` | Every tab must fit both the viewport and its cards at phone and desktop widths. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Tests: core

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `tests/core/test_adult_example.py` | Offline tests for the UCI Adult real-data example. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_certificate_scale.py` | Fix #5 — the fairness score is measured, and its denominator is disclosed. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_continuous_fairness.py` | Chaos evidence, model comparison, release-gate, and report tests. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_dataset_integrity.py` | Fail-closed Adult input verification, bounded downloads, and atomic cache writes. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_decision_contract.py` | All metric entry points share a strict, non-truthiness decision contract. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_equal_opportunity_reliability.py` | The equal-opportunity gap must rest on enough *qualified* people, not rows. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_metrics.py` | Regression tests for ChaosHire&#x27;s fairness calculations. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_review_honesty.py` | Red-flag review: what the product says about itself must match what it is. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_statistics.py` | Statistical-rigor and intersectional-audit tests. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_threshold_contrast.py` | Fix #3 — per-group threshold calibration is a research contrast, not a fix. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_trained_model.py` | The bundled trained model: pinned artifact integrity and end-to-end auditability. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/core/test_workflows.py` | End-to-end tests for the main product workflows. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Tests: infrastructure

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `tests/infrastructure/test_build_info.py` | The committed build facts must match a real test run. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_connector_validation.py` | Safe remote configuration and 502 verdicts for invalid external decision contracts. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_distribution_check.py` | The install gate detects broken identity, dependency, CLI, license and asset metadata. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_log_shipping.py` | Real delivery paths and deterministic load tests for the bounded webhook pool. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_portfolio_platform.py` | Days 11-20: agent, adapters, security, evidence, PDF, operations, and demo. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_postgres_adapter.py` | Tests for the optional PostgreSQL repository adapter. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_repository.py` | Persistent aggregate audit-history tests. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_repository_inventory.py` | The repository-wide inventory fails usefully instead of promising formal verification. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_resource_bounds.py` | Limiter identities expire globally and flooding cannot reset an active budget. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/infrastructure/test_security_connectors.py` | Nonce-based CSP and the operator-configured remote decision connector. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Tests: integration

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `tests/integration/conftest.py` | Opt-in database tests touch only a random schema on an explicit local test service. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/integration/test_postgres.py` | Service-backed schema, transactional, dispatcher, and HTTP readiness verification. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Tests: shared fixtures

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `tests/conftest.py` | Shared test isolation for in-memory application state and SQLite history. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Tests: web

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `tests/web/test_external_css.py` | Tests for the external CSS migration and CSP style-src hardening. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/web/test_external_js.py` | The dashboard&#x27;s markup and behavior ship separately without weakening CSP. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/web/test_html_escaping.py` | Fix #1 — HTML escaping and the nonce-based Content-Security-Policy. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |
| `tests/web/test_site_readiness.py` | Public site/SEO, consented analytics, security and anti-spam contracts. | UTF-8/nonempty; limited secret-signature scan; Python AST | PASS |

## Web assets

| File | Responsibility | Structural checks | Result |
|---|---|---|---|
| `chaoshire/web/404.html` | 404.html | UTF-8/nonempty; limited secret-signature scan; HTML ids/anchors/local assets | PASS |
| `chaoshire/web/index.html` | index.html | UTF-8/nonempty; limited secret-signature scan; HTML ids/anchors/local assets | PASS |
| `chaoshire/web/privacy.html` | privacy.html | UTF-8/nonempty; limited secret-signature scan; HTML ids/anchors/local assets | PASS |
| `chaoshire/web/static/chaoshire.css` | Responsive styles, typography and accessibility states | UTF-8/nonempty; limited secret-signature scan; CSS asset references | PASS |
| `chaoshire/web/static/chaoshire.js` | Dashboard behavior; markup and styles live in separate files | UTF-8/nonempty; limited secret-signature scan; Node.js syntax | PASS |
| `chaoshire/web/static/fonts/OFL.txt` | OFL.txt | UTF-8/nonempty; limited secret-signature scan | PASS |
| `chaoshire/web/static/fonts/SUBSET.txt` | SUBSET.txt | UTF-8/nonempty; limited secret-signature scan | PASS |
| `chaoshire/web/static/fonts/besley-latin.woff2` | Self-hosted heading font; OFL license alongside it | WOFF2 header/length/license notices | PASS |
| `chaoshire/web/static/icons/favicon-32.png` | Browser icon or social-sharing image | PNG chunks/CRC/dimensions | PASS |
| `chaoshire/web/static/icons/favicon.ico` | Browser icon or social-sharing image | ICO directory/image bounds | PASS |
| `chaoshire/web/static/icons/icon-192.png` | Browser icon or social-sharing image | PNG chunks/CRC/dimensions | PASS |
| `chaoshire/web/static/icons/icon-512.png` | Browser icon or social-sharing image | PNG chunks/CRC/dimensions | PASS |
| `chaoshire/web/static/icons/icon-maskable-512.png` | Browser icon or social-sharing image | PNG chunks/CRC/dimensions | PASS |
| `chaoshire/web/static/social-preview.png` | Browser icon or social-sharing image | PNG chunks/CRC/dimensions | PASS |
| `chaoshire/web/terms.html` | terms.html | UTF-8/nonempty; limited secret-signature scan; HTML ids/anchors/local assets | PASS |
