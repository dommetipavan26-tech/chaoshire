# Changelog

All notable changes to ChaosHire will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [Unreleased]

### Fixed
- Model selector now opens the fairness dashboard, preventing the static LegacyCorp landing example from appearing to represent both models
- Updated the landing proof strip to the verified v0.21.0 public release
- Added `HEAD` support to health, liveness, and readiness endpoints for UptimeRobot and other uptime monitors

### Added
- Recruiter-first landing page with direct Guided Demo and Dashboard entry points, verified engineering proof, project links, and an explicit responsible-use boundary
- Deterministic scikit-learn logistic-regression decision-adapter example using 800 synthetic candidates
- Playwright automation covering a 390 px mobile viewport, recruiter proof, CTA behavior, and keyboard activation
- Reproducible desktop/mobile screenshot capture plus a three-minute demo script and résumé-ready project descriptions
- Automated tag-driven GitHub releases with source, HTML/PDF reports, evidence, and SHA-256 checksums
- Weekly CodeQL and dependency-vulnerability scanning plus Dependabot updates
- Render free-tier blueprint, UptimeRobot runbook, release checklist, architecture diagram, and recruiter-facing case study
- Deterministic, evidence-grounded Fairness Review Agent with prioritized findings and human-action plans
- Pluggable `DecisionAdapter` contract for reference models, CSV outcomes, and in-process providers
- Optional `X-API-Key` protection for mutation routes without breaking the open portfolio demo
- Request IDs, security headers, body-size enforcement, optional rate limiting, readiness, liveness, and operational metrics
- Canonical SHA-256 aggregate evidence bundles with tamper-verification API and CLI
- Dependency-free native PDF audit summaries through API and CLI
- Accessible mobile/PWA shell with offline app-shell caching and network-first audit evidence
- Stable six-step, three-minute guided portfolio demonstration in the API and dashboard
- Sixteen Days 11–20 regression tests; suite now contains 65 tests with more than 96% coverage
- Reusable `ChaosTest` experiment interface with normalized observations and verdict policies
- Deterministic SHA-256 experiment IDs for reproducible model-and-policy runs
- Candidate-level before/after score and decision evidence, capped from 0–50 records
- Configurable PASS/WARN/FAIL thresholds through `POST /api/chaos/run`
- Side-by-side reference model comparison through `GET /api/compare`
- Automated absolute-floor and regression checks through `POST /api/gate`
- CI-compatible command line (`python -m chaoshire gate`) with PASS=0 and BLOCK=1 exit codes
- Dedicated GitHub Actions fairness-release-gate workflow
- Self-contained offline HTML reports through API and CLI
- Release Gate dashboard tab and expandable Chaos Lab evidence tables
- Continuous-fairness architecture and integration documentation
- Eleven continuous-fairness regression tests; suite now contains 49 tests with more than 96% coverage
- SQLite-backed aggregate audit repository with random audit IDs, names, UTC timestamps, and provenance
- Audit history and detail endpoints (`/api/audits`, `/api/audits/{audit_id}`)
- Audit History dashboard tab with summary and detail views
- Explicit storage boundary: raw uploaded rows remain in memory and are never written to audit history
- Database-path configuration, Docker write permissions, and persistence/privacy documentation
- Six persistence and privacy regression tests; suite now contains 38 tests with more than 95% coverage
- Two-sided 95% Wilson confidence intervals for selection rates and true-positive rates
- Exploratory pooled two-proportion significance tests for highest-vs-lowest selection groups
- Pairwise intersectional audits for every selected protected-attribute combination
- Dedicated statistical methodology and limitations guide
- Intersectional-risk dashboard cards that keep low-sample groups visible and marked
- Seven statistical regression tests; suite now contains 32 tests with more than 95% coverage
- Configurable bring-your-own-model audits for custom outcome, qualification, candidate-ID, and protected-attribute columns
- Configurable favorable/qualified values and minimum reliable group size
- Upload warnings for missing values, absent IDs, one-class decisions, and single-group attributes
- High-cardinality attribute guard and actionable missing-column responses
- Downloadable JSON audit reports from `/api/audit/export`
- Mobile-friendly upload configuration UI with detected-header preview and explicit privacy warning
- Six configurable-upload regression tests; suite now contains 25 tests with more than 95% coverage
- Modular `chaoshire` Python package with dedicated data, model, metric, chaos, schema, service, state, and route layers
- Ruff linting and a 90% minimum coverage gate in GitHub Actions
- End-to-end tests for explanations, filtered candidates, appeals, uploads, mitigations, and repeatable chaos experiments
- Organized OpenAPI tags and bounded request validation

### Changed
- Renamed user-facing “Fairness Certificate” terminology to “Fairness Risk Score” to avoid implying independent or legal certification
- Retained historical `certificate` JSON fields and `--min-certificate` CLI options for backward compatibility
- `backend.py` is now a backward-compatible deployment shim; `uvicorn backend:app` remains supported
- Privilege-keyword injection now uses a local deterministic random generator, so repeated Chaos Lab calls are identical
- Test suite expanded from 12 to 19 tests with more than 97% package coverage

### Planned
- User accounts and auditor/reviewer roles
- Durable managed-database adapter
- Authenticated remote model connector
- External log shipping and long-term metrics
- SHAP-compatible explanation adapter

## [0.1.0] - 2026-09-06

### Added
- Deterministic 1,000-candidate synthetic demonstration
- LegacyCorp and MeritFirst reference scoring models
- Disparate-impact, demographic-parity, and equal-opportunity analysis
- Five-test counterfactual Chaos Lab and resilience score
- Candidate explanations, mitigation simulations, and appeals workflow
- CSV outcome upload and sample dataset download
- Responsive web dashboard and public Render deployment
- API health endpoint, automated tests, GitHub Actions, and Docker support

### Documentation
- Professional quick-start and responsible-use guidance
- Explicit disclosure that all built-in people, employers, and results are synthetic
- Methodology limitations and product roadmap
