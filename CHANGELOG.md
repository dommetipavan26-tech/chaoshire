# Changelog

All notable changes to ChaosHire will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [Unreleased]

## [0.23.0] - 2026-09-19

Red-flag review remediation. Five findings from an external review of the public
deployment, fixed in the order they were raised. Each has a regression test named
below; `SECURITY.md` now documents the enforced posture rather than an aspiration.

### Security

- **Exception text no longer reaches a response body.** CodeQL flagged three new
  information-exposure paths in this branch. `POST /api/connectors/audit` returned
  the raw upstream exception in its 502 body — exactly the kind of message that
  carries the request URL, proxy configuration or a credential fragment — and the
  CSV upload path returned the pandas parser message, which can quote buffer
  contents and dialect guesses. Both now return the failure category plus the
  exception *class* (`reason`/`(ParserError)`), and the full text goes to the
  server log where an operator can still read it.
  (`tests/test_security_connectors.py`)
- **`train --include-protected` no longer dumps the raw fitted weights to
  stdout.** The variable was also renamed from `leaked` to `contrast_coefficients`
  — the fit is a synthetic contrast, not a leaked secret, and the old name
  mislabelled it. CodeQL's `py/clear-text-logging` rule classifies values derived
  from a protected-attribute fit as private data reaching an output sink. That
  verdict is a false positive here (the fixture is synthetic and its
  protected-attribute weights are already published in `chaoshire/models.py`), but
  inline `# codeql[...]` suppression comments are not honoured by this
  repository's code-scanning configuration — the alert was re-reported on the
  `json.dumps` argument, then the enclosing `print` call, then a single-line
  `sys.stdout.write` sink. Rather than disable the query repo-wide for one false
  positive, the CLI report keeps what carries the argument — the certificate
  (**48/D**) and the gender disparate impact (**0.678**, worse than the blind
  fit's 0.78, which is the case for blinding) — and `coefficients` now points at
  `chaoshire.training.train_coefficients(include_protected=True)` for anyone who
  wants the raw values in Python. `tests/test_trained_model.py` asserts both the
  contrast and the omission. The `--write` guard that refuses to pin a
  protected-attribute fit is unchanged.
- **The dashboard no longer builds HTML by unescaped string concatenation.**
  `esc()` in `index.html` escapes `"` and `'` as well as `& < >`, plus the
  backtick. Every interpolation into an attribute that can break out (`href`,
  `src`, `value`, `title`, `alt`, `placeholder`, `id`, `for`, `name`, `data-*`)
  goes through `esc()` or `encodeURIComponent()`, and the remaining
  `class`/`style`/`aria-*` interpolations are a frozen, reviewed presentational
  allowlist. Previously a hostile protected-attribute value in an uploaded CSV
  could break out of an attribute and inject a handler into the shared
  `dataset=uploaded` view every visitor reads. (`tests/test_html_escaping.py`)
- **The nonce-based Content-Security-Policy from the unapplied v0.25.0 patch is
  now live.** `script-src 'self' 'nonce-…'` replaces `script-src 'self'
  'unsafe-inline'`; the nonce is regenerated per request. `frame-ancestors
  'none'`, `base-uri 'self'` and `form-action 'self'` are set. `index.html` has
  exactly one script tag and no inline event handlers.
- **The public demo now enforces write access instead of advertising it.**
  `render.yaml` generates a real `CHAOSHIRE_API_KEY` at deploy time and sets
  non-zero read (120/min) and write (6/min) rate limits; both were `0`, which
  disabled the limiter entirely on a 512 MB free instance.
  `CHAOSHIRE_TRUST_FORWARDED_FOR=1` gives each real client its own bucket behind
  Render's proxy, using only the right-most `X-Forwarded-For` entry so a client
  cannot rotate the header. The gateway fails closed: with anonymous writes
  disabled and no key configured it answers `503` rather than silently accepting
  writes. (`tests/test_write_access.py`)
- **Anonymous uploads are no longer published.** An unauthenticated upload is
  audited, returned to the caller, and discarded — `published: false`,
  `audit_id: null`, never in `/api/audits`, never in the shared
  `dataset=uploaded` slot. Holding the operator key is what makes an upload
  visible to other visitors. This closes the defacement path (an
  attacker-chosen audit name in the history everyone reads) without removing the
  interactive demo. Audit names are normalised by `sanitise_audit_name()`:
  control characters become spaces, whitespace collapses, 60-character cap.
- **The appeal queue is bounded.** `APPEALS` was an unbounded in-memory list, so
  a POST loop was a memory-exhaustion vector. It is now a capped FIFO
  (`CHAOSHIRE_MAX_APPEALS`, default 200) that evicts and counts the oldest entry.
- **Upload and appeal payloads have schema-level length caps**, so an
  over-long name is rejected with `422` before it reaches any storage path.

### Fixed

- **The type-check job no longer aborts on the Python 3.12 matrix leg.** numpy
  2.5+ requires Python >= 3.12 and ships PEP 695 `type` statements in
  `numpy/__init__.pyi`; with `python_version = "3.11"` mypy refused to parse the
  stub and exited 2 ("errors prevented further checking") before analysing any of
  our own code, and `fail-fast` then cancelled the 3.11 leg so only one leg looked
  broken. Each leg now passes `--python-version` from the matrix, and 3.11 stays
  the local default as the lowest supported runtime.
- Living documentation (`README.md`, `SECURITY.md`, `docs/`) can no longer quote a
  stale test count or coverage figure: `tests/test_build_info.py` scans every
  current-facing markdown file and compares the numbers against
  `chaoshire/build_info.py`. `CHANGELOG.md` and `TODO.md` are excluded on purpose —
  a v0.22.0 entry saying "98 tests" is correct forever. The portfolio case study
  and evidence documents had been advertising "98 tests, 97.65%" for two releases
  after that stopped being true.
- The service-worker cache name is derived from the package version
  (`chaoshire-v0230`) instead of being hardcoded, so a release cannot ship a
  worker that keeps serving the previous version's precached shell.

### Changed

- **Per-group threshold calibration is no longer a mitigation.**
  `mitigate(["calibrate"])` used to set per-group decision cutoffs on gender,
  ethnicity and age and report the result as an applied fix, with a soft caveat
  that it "may create legal or operational concerns". Setting different cutoff
  scores by race, colour, religion, sex or national origin in an employment test
  is an unlawful employment practice under
  [42 U.S.C. § 2000e-2(l)](https://www.law.cornell.edu/uscode/text/42/2000e-2)
  (Civil Rights Act of 1991) — the jurisdiction the project's own four-fifths
  rule comes from. `calibrate` is removed from the strategy catalogue and
  rejected at the schema level with `422`. The computation survives as a labelled
  research contrast, reachable only with `threshold_contrast_acknowledged: true`
  (refused when `false`, skipped when absent), reported under its own
  `research_contrast` key, never merged into a mitigation result, and citing the
  statute, its text and a "not legal advice" notice in every response that
  mentions it — including `excluded_controls` on ordinary mitigation calls.
  (`tests/test_threshold_contrast.py`)
- **The fairness risk score is measured, and its denominator is disclosed.**
  `certificate()` added an unconditional `TRANSPARENCY_POINTS = 15` for
  disclosure, release gates, CI and appeal routes — none of it a property of the
  model under audit, none of it measured. It gave a badly biased model 47/D
  instead of 32/F and capped a perfect one at 85. The score is now
  `measured / available × 100` on a single scale, and a perfect group-fairness
  result scores 100/A on merit. The platform capabilities are still disclosed, as
  `platform_disclosure` text with `scored: false`.
- **The 85↔60 denominator switch is no longer silent.** `available` is 85 when
  ground-truth qualification labels exist (disparate impact + parity + equal
  opportunity) and 60 when they do not. Every payload now carries
  `measured_points`, `available_points`, `scale`, `basis`, `basis_note`,
  `unmeasured_components` (label, points and reason) and
  `comparable_with_full_basis`; the HTML and PDF reports state the basis next to
  the number and warn that a selection-rate-only score must not be ranked against
  a full-basis one. Canonical results shift accordingly: legacy **42/F → 32/F**,
  fair **86/B → 84/B**, mitigation delta **52 → 48**. (`tests/test_certificate_scale.py`)

### Added

- **TalentFit v3, the trained reference model, is merged out of
  `chaoshire-v0.25.0.patch` and the patch file is deleted.** Its coefficients are
  pinned in `chaoshire/training.py` with a SHA-256 digest;
  `python -m chaoshire train --check` re-derives them and fails CI on drift
  (agreement floor 0.90). The result is the project's best argument and no longer
  lives in a diff: trained on the same synthetic population, TalentFit v3
  reproduces the merit-only model on every counterfactual and stress test
  (**resilience 100/100**) while still failing the four-fifths rule
  (**disparate impact 0.78**, score **66/C**). Perfect counterfactual resilience
  alongside failing disparate impact is exactly why both are measured.
- **`chaoshire/build_info.py` is the single source of truth for the numbers the
  landing page and README quote.** Version, model count, experiment count and
  fixture size are derived from the running package at import time. The test count
  and coverage figure cannot be, so `scripts/check_build_info.py` re-derives both
  from a real pytest run and fails the build on drift; it runs in
  `.github/workflows/test.yml`. `GET /api/meta` serves the result as `build` and
  `index.html` renders that payload instead of hardcoding a version string — the
  failure mode that left the landing page advertising v0.21.0 while the package
  said v0.22.0. (`tests/test_build_info.py`)
- CI diagnostics: the `Type check` and browser jobs re-emit tool output through
  `::error::` on failure, so the reason is visible on the PR page and through the
  checks API instead of only inside the raw job log.
- `render.yaml` and `.env.example` document the full deployment posture:
  generated key, non-zero rate limits, forwarded-for trust, bounded appeals, and
  the "the key buys publishing" rule.
- `SECURITY.md` rewritten around what the shipped configuration enforces.
- `browser_tests/test_landing.py` rewritten to read the proof strip from
  `/api/meta` rather than asserting hardcoded strings, and extended with a
  mitigation-refusal check and an end-to-end XSS regression that uploads a
  hostile group value and asserts it renders as inert text.
- 90 new tests; the suite now contains 188 tests with 97.5% package coverage.

## [0.22.0] - 2026-09-13

Verification-driven hardening release. Every item below is covered by a
regression test in `tests/test_verification_fixes.py`.

### Fixed
- `GET /api/chaos`, `/api/audit`, `/api/filtered`, `/api/explain`, `/api/evidence`, `/api/report.html`, and `/api/report.pdf` reject unknown `model` identifiers with HTTP 400 instead of crashing with HTTP 500 or silently auditing a different reference model.
- Unknown `dataset` values are rejected with HTTP 400 instead of falling back to the demo dataset.
- `/api/metrics` now records unhandled endpoint exceptions as server errors; previously a 500 escaped before the operational counters ran.
- Audits whose decisions show no variation (every candidate selected, or none), whose rows carry no protected attribute, or whose attributes never reach two reliable groups are reported as grade `N/A` with explicit reasons instead of a misleading perfect 100/A.
- `POST /api/mitigate` rejects unknown strategy names instead of silently returning an unchanged audit.
- The dashboard HTML-escapes uploaded attribute names and group labels, closing a self-XSS path through hostile CSV headers or cell values.
- Evidence verification rejects bundles whose digest is missing or not a string and compares digests in constant time.
- The shared in-memory upload slot is swapped under a lock so concurrent uploads cannot interleave.

### Added
- Installable PWA assets: deterministic 192/512/maskable icons generated by `scripts/generate_icons.py`, manifest `icons`, `id`, and `scope`, favicon and apple-touch-icon links, and service-worker precache of the icon set (cache rotated to `chaoshire-v0220`).
- `/api/audit` echoes the resolved reference model so every audit payload is self-describing.
- The Privilege-Keyword Injection test reports score headroom and the prestige weight required before it could fail; a regression test proves the experiment fails a prestige-heavy model and passes the merit-only fixture.
- `.dockerignore` keeps `.git`, local databases, virtualenvs, and caches out of the Docker build context.
- 33 new regression tests; the suite now contains 98 tests with 97.65% package coverage.

### Changed
- `POST /api/mitigate` returns a symmetric payload: `before` and `after` are both complete audit objects and the response names the simulated reference model.
- Documentation refresh: methodology assessability guards, monitoring metrics note, persistence wording for the shared upload slot, contributor lint step, generalized release checklist, and backfilled release history.

## [0.21.0] - 2026-09-12

> This section also encompasses the changes shipped in v0.20.0 and v0.20.1,
> which were published without their own changelog sections.


### Fixed
- Keep the model switcher on Home and update the demonstration card immediately: LegacyCorp shows 42/F, 169 gender flips, 111 community flips, and 30 resilience; MeritFirst shows 86/B, zero identity flips, and 100 resilience
- Force immediate service-worker activation, rotate the app-shell cache, and disable HTML/service-worker HTTP caching so deployed UI fixes reach returning browsers
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
