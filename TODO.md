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
- [x] `train --include-protected` no longer dumps raw fitted weights to stdout; resolves the CodeQL `py/clear-text-logging` false positive without disabling the query repo-wide
- [ ] Revisit the `py/clear-text-logging` deviation in SECURITY.md if CodeQL starts honouring inline suppression comments
- [ ] Dismiss or re-review the CodeQL alert if the repository ever handles real candidate data
- [x] 90 new tests (suite: 188 tests, 97.5% coverage)
- [ ] Push the v0.23.0 tag and confirm the automated GitHub release
- [ ] Verify the Render deployment picks up the generated `CHAOSHIRE_API_KEY` and that `/api/ready` passes the health check

## Future engineering

- [ ] Per-audit access control so published uploads are not world-readable
- [ ] Move `style-src 'unsafe-inline'` out of the CSP by externalising the inline stylesheet
- [ ] User accounts and auditor/reviewer roles
- [ ] Managed PostgreSQL repository
- [ ] Authenticated remote model connector
- [ ] Durable metrics and external log shipping
- [ ] Dependency and container vulnerability scanning
- [ ] SHAP-compatible explanation adapter
