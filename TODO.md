# ChaosHire portfolio backlog

## Release v0.20.0

- [x] Evidence-grounded fairness review agent
- [x] Pluggable decision-source adapter contract
- [x] Optional API-key protection for mutation routes
- [x] Request IDs, security headers, size limits, and optional rate limiting
- [x] Liveness, readiness, and operational metrics
- [x] Tamper-evident SHA-256 aggregate evidence bundles
- [x] Native PDF summary export
- [x] Mobile accessibility and installable PWA shell
- [x] Stable three-minute guided demo
- [x] Full regression suite and documentation
- [x] Push v0.20.0 implementation and confirm quality/fairness workflows
- [x] Add automated security scanning and release workflow
- [x] Add Render blueprint, monitoring runbook, architecture diagram, and case study
- [ ] Verify Render v0.20.0 on a physical phone
- [ ] Configure UptimeRobot alert contacts in the owner's account
- [x] Push the v0.20.0 tag and confirm the automated GitHub release

## Release v0.22.0

- [x] Verification-driven hardening: strict model/dataset validation, honest 500 accounting, non-assessable audit verdicts, mitigation contract hardening, dashboard escaping, evidence-verification robustness, upload-slot locking
- [x] Installable PWA icons and manifest metadata
- [x] 33 new regression tests (suite: 98 tests, 97.65% coverage)
- [ ] Push the v0.22.0 tag and confirm the automated GitHub release

## Release v0.23.0 — red-flag review remediation

- [x] Escape `"` and `'` in `esc()`, route every breakout-attribute interpolation through `esc()`/`encodeURIComponent()`, and apply the nonce-based CSP from the unapplied v0.25.0 patch (`tests/test_html_escaping.py`)
- [x] Merge `chaoshire-v0.25.0.patch` — TalentFit v3 pinned in `chaoshire/training.py` with a SHA-256 digest and a `train --check` CI gate — and delete the patch file
- [x] Remove per-group threshold calibration from the mitigation set; reframe as a research-only contrast refused by default and citing 42 U.S.C. § 2000e-2(l) (`tests/test_threshold_contrast.py`)
- [x] Generate `CHAOSHIRE_API_KEY` on the public demo, set non-zero read/write rate limits, trust forwarded-for behind the proxy, and bound the appeal queue (`tests/test_write_access.py`)
- [x] Delete the unconditional +15 transparency points; score `measured / available × 100` and disclose the 85↔60 denominator switch (`tests/test_certificate_scale.py`)
- [x] `chaoshire/build_info.py` as the single source of truth for quoted numbers, served via `/api/meta`, with `scripts/check_build_info.py` failing CI on drift (`tests/test_build_info.py`)
- [x] `render.yaml` and `.env.example` document the enforced deployment posture
- [x] `SECURITY.md` rewritten around what the shipped configuration actually enforces
- [x] `browser_tests/test_landing.py` reads the proof strip from `/api/meta` and adds a mitigation-refusal plus end-to-end XSS regression
- [x] Exception text no longer reaches a response body; upstream and CSV-parse failures return the category plus the exception class and log the detail (CodeQL `py/stack-trace-exposure`)
- [x] Per-leg `--python-version` for mypy so numpy 2.5's PEP 695 stubs do not abort the 3.12 leg
- [x] Living documentation scanned for stale test/coverage figures (`tests/test_build_info.py`)
- [x] Service-worker cache name derived from the package version
- [x] CI re-emits mypy and browser-check output as workflow annotations on failure
- [x] `train --include-protected` writes its report to `reports/generated/protected-contrast.json` and prints only a static acknowledgement; a better channel for a machine-readable report, though it moves the false positive from `py/clear-text-logging-sensitive-data` to `py/clear-text-storage-sensitive-data` rather than clearing it
- [x] Dismiss the `py/clear-text-storage-sensitive-data` alert on `chaoshire/cli.py` as a false positive in the code-scanning UI (reasoning recorded in SECURITY.md → Static analysis); both clear-text queries stay enabled for the rest of the package
- [ ] Revisit the false-positive dismissal in SECURITY.md if CodeQL starts honouring inline `# codeql[...]` suppression comments
- [ ] Re-review that dismissal before any deployment that handles real candidate data
- [x] 90 new tests (suite: 188 tests, 97.5% coverage)
- [x] Push the v0.23.0 tag and confirm the automated GitHub release
- [x] Verify the Render deployment picks up the generated `CHAOSHIRE_API_KEY` and that `/api/ready` passes the health check

## Release v0.23.1 — verifiable write posture

- [x] `/api/meta` discloses `trusted_proxy_headers` and `rate_limit_bucketing`; the note names `CHAOSHIRE_TRUST_FORWARDED_FOR` and explains that with it unset every visitor shares one bucket (`tests/test_write_access.py`)
- [x] Boot log line `chaoshire 0.23.1 resolved write posture: {...}` — booleans and safe scalars only, the key value never reaches the log (`tests/test_write_access.py`)
- [x] `docs/MONITORING.md` Render runbook: Blueprint vs hand-managed env, verify method per variable, local key generation, Blueprint-adoption risk, and the audit-history ephemerality options
- [x] Owner action: set `CHAOSHIRE_API_KEY` on the hand-created Render service (render.yaml is not synced to it)
- [x] Owner action: set `CHAOSHIRE_TRUST_FORWARDED_FOR=1` on the hand-created Render service
- [x] Verified live: a wrong `X-API-Key` gets `401`, so the generated key is picked up
- [x] Verified live: anonymous upload → `200` with `published: false` and no `audit_id`
- [x] Verified live: `/api/meta` shows `trusted_proxy_headers: true` / `per-client-ip`, rate limits `120`/`6`, and appeals capacity `200`
- [ ] Open decision: adopt the `render.yaml` Blueprint (a second service means a new URL and every `chaoshire.onrender.com` link breaks) or keep hand-managing the environment on the existing service
- [ ] Open decision: audit-history persistence posture on the free plan (stay ephemeral / external managed store / periodic export)
- [ ] Push the v0.23.1 tag and confirm the automated GitHub release

## Release v0.23.2 — drawback remediation

- [x] Stop calling `logging.basicConfig` at import; last-resort handler is logger-local in lifespan
- [x] Gate `/api/meta` recon fields behind `CHAOSHIRE_DISCLOSE_WRITE_POSTURE` (default follows anonymous-writes); full posture on `GET /api/ops/posture`
- [x] Prove left-most XFF with `/api/ops/whoami`, unit tests, `scripts/probe_xff.py`, and a process-wide `write:_instance` backstop
- [x] Boot log uses literal ternaries only; tests assert tokens, not the whole line
- [x] `ANONYMOUS_UPLOADS_PUBLISHED` is the single source for that fact
- [x] Disclose `audit_history_durable` (default false) and warn at boot; persistence still requires a paid disk or managed DB
- [x] Disclose `limiter_scope=process-local-memory` and warn when `WEB_CONCURRENCY`/`UVICORN_WORKERS` > 1
- [x] Boot reports `blueprint_drift` versus the committed `render.yaml` contract
- [x] Anonymous appeals evicted before authenticated ones; extra anonymous appeal budget
- [x] Roadmap no longer claims untagged releases
- [x] `HEAD /` returns 200
- [ ] Push the v0.23.2 tag (and the still-missing v0.23.1 / v0.22.0 tags)

## Release v0.23.3 — continue red-flag 1–40

Re-applied on `main` at `cc1636a` (v0.23.2) — the previous sandbox's `0ad1125`/`4a4ba98` branch from `ce2c4f0` was not pushed and conflicts if cherry-picked. Owner-only work is not faked; scores `32/F` and `30/100` are preserved.

- [x] Fix docs drift: `.env.example`, `docs/PORTFOLIO-PLATFORM.md`, `docs/MONITORING.md`, `SECURITY.md` now say **left-most** X-Forwarded-For (code: `platform.client_key` → `candidates[0]` + `canonical_ip`) and document the `write:_instance` cap
- [x] Fix `docs/PORTFOLIO-PLATFORM.md` deployment example (`0` → `120` read budget and every Blueprint var)
- [x] Correct coverage-figure drift (`98.4%` → `98.3%`); `chaoshire/build_info.py` stays at `201 tests / 98.3%` via `scripts/check_build_info.py`
- [x] Correct roadmap tag claim to `v0.22.0, v0.23.1 and v0.23.2 tags pending owner`
- [x] Preserve `audit(legacy) == 32/F` and `chaos(legacy).resilience == 30/100` (169 gender, 111 community flips) — no coefficient/threshold change
- [x] Do **not** fake owner-only: no new tags, no synthetic UptimeRobot monitor, no CodeQL inline suppression, no `disk:` on `plan: free`, no paid Redis/Postgres, no `control.py` commit; ephemerality and limitations stay documented in `SECURITY.md`/`docs/MONITORING.md`/`docs/PERSISTENCE.md`
- [x] `HEAD /` and `HEAD /api/health|/live|/ready` → `200`; CSP nonce per-request, no `unsafe-inline` for scripts, `esc()` covers `& < > \" '` + backtick
- [x] Verify `python -m pytest -q` (201), `--cov` (98.3%), `mypy` (3.11/3.12 clean), `check_build_info.py` (--coverage-json) and `GET /api/meta`/`/api/ops/*` live checks
- [ ] Push the v0.23.3 tag (and the still-missing v0.23.2 / v0.23.1 / v0.22.0 tags) — owner

## Release v0.23.4 — finish red-flag 1–40

Closes the five items still visible on the v0.23.3 live deployment. Scores `32/F` and `30/100` preserved; owner-only work is not faked; history untouched.

- [x] Chaos Lab stories rewritten from marketing narrative (“Does the model get gamed?”, “Who survives?”) to method text; gap/age-stress details no longer claim “Detects hidden ageism” or “Disproportionately impacts…” (`tests/test_review_honesty.py`)
- [x] Privilege-injection verdict labelled `fixture-limited` (payload field + Chaos Lab chip + scope note + README/`docs/CONTINUOUS-FAIRNESS.md`); no verdict or resilience-score change
- [x] “Fairness Review Agent” renamed to **Fairness Review** (rules engine, not an AI agent) in the payload name, dashboard tab, demo step 4, CLI help, README and `docs/PORTFOLIO-PLATFORM.md`; `/api/agent/review` kept for compatibility; historical records untouched
- [x] TalentFit blurb states the measured outcome (resilience 100/100 vs 66/C, DI 0.78) instead of a teaser question
- [x] `GET /api/appeals` serves redacted copies (`chaoshire/redaction.py`): names → initials, emails/7+ digit runs/phone-like runs → fixed placeholders, rules disclosed in the payload and the UI; `SECURITY.md` + `docs/PORTFOLIO-PLATFORM.md` document the limits (`tests/test_appeals_redaction.py`)
- [x] Do **not** fake owner-only work: no tags, no UptimeRobot, no CodeQL inline suppression, no `disk:` on `plan: free`, no paid Redis/Postgres, no `control.py` commit
- [x] Verify `python -m pytest -q` (216), `--cov` (98.4%), `ruff format --check`/`ruff check`, `mypy` (3.11/3.12 clean), `check_build_info.py` (--coverage-json), and a local smoke of `/api/appeals`, `/api/chaos`, `/api/agent/review`, `/api/meta`, `HEAD /`
- [ ] Push the v0.23.4 tag (and the still-missing v0.23.2 / v0.23.1 / v0.22.0 tags) — owner

## Future engineering

- [ ] Per-audit access control so published uploads are not world-readable
- [ ] Move `style-src 'unsafe-inline'` out of the CSP by externalising the inline stylesheet
- [ ] User accounts and auditor/reviewer roles
- [ ] Managed PostgreSQL repository
- [ ] Authenticated remote model connector
- [ ] Durable metrics and external log shipping
- [ ] Dependency and container vulnerability scanning
- [ ] SHAP-compatible explanation adapter
