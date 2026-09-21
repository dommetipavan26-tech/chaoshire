# Changelog

All notable changes to ChaosHire will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [Unreleased]

## [0.24.0] - 2026-09-21

Future engineering items from `PROJECT-ROADMAP.md` and `TODO.md` — external
CSS, JSON log shipping, optional Postgres adapter, SHAP-compatible
explanations, and marking the remote REST connector as shipped. LegacyCorp
stays **32/F** and Chaos stays **30/100** (169 gender, 111 community flips).
Owner-only work is **not** faked; history untouched.

### Added

- **External CSS.** The `<style>` block was extracted to
  `chaoshire/static/chaoshire.css` and served at `/static/chaoshire.css`
  with a long cache. Static inline `style=""` attributes in the HTML body
  were replaced with utility classes; dynamic values in JavaScript template
  literals use `data-style=""` and are applied via CSSOM after `innerHTML`
  (which is not restricted by `style-src`). The CSP now reads
  `style-src 'self'` — `'unsafe-inline'` is dropped from both `script-src`
  and `style-src`. (`tests/test_external_css.py`)
- **Structured JSON log shipping.** `chaoshire/loghook.py` POSTs structured
  events to `CHAOSHIRE_LOG_WEBHOOK_URL` on a background thread. Events
  shipped: `audit.completed`, `appeal.created`, `chaos.completed`,
  `mitigation.completed`, `upload.completed`. Optional HMAC-SHA256
  signature via `CHAOSHIRE_LOG_WEBHOOK_SECRET`. Failures are logged but
  never block the request; the queue is bounded. `/api/meta` reports
  `log_shipping` status. (`tests/test_log_shipping.py`)
- **Optional PostgreSQL adapter.** `chaoshire/repository_postgres.py`
  implements the same interface as the SQLite backend, activated by
  `CHAOSHIRE_DB_BACKEND=postgres` and `CHAOSHIRE_DATABASE_URL`. SQLite
  stays the zero-config default. Lazy `psycopg2` import means the
  dependency is only required on deployments that opt in.
  (`tests/test_postgres_adapter.py`)
- **SHAP-compatible explanation adapter.** `chaoshire/explain.py` produces
  SHAP-compatible feature-attribution vectors (`base_value` + per-feature
  `values` + `feature_names`) for any reference model, without depending on
  the `shap` package itself. Routes: `GET /api/explain/shap/{id}` and
  `POST /api/explain/shap/batch`. Listed in `/api/adapters`.
  (`tests/test_shap_adapter.py`)
- **Remote REST connector marked done.** `RemoteDecisionAdapter` in
  `chaoshire/adapters.py` (shipped in v0.20.0) implements the
  authenticated HTTP connector; `PROJECT-ROADMAP.md` and `TODO.md` now
  reflect that.

### Changed

- Version `0.23.4` → `0.24.0`; `chaoshire/build_info.py` reports **270
<<<<<<< HEAD
  tests and 94.7%** package coverage (the new modules expand the surface
=======
  tests and 94.7%** package coverage (the new modules expand the surface
>>>>>>> ce80706 (fix(ci): correct coverage figure to 94.7% and add ±0.1% tolerance to build_info check)
  without reducing the 90% gate).
- `README.md`, `docs/PORTFOLIO-CASE-STUDY.md`, `docs/PORTFOLIO-EVIDENCE.md`
  quote the same figures.
- `PROJECT-ROADMAP.md` and `TODO.md` mark the remote REST connector,
  optional Postgres adapter, log shipping, external CSS and SHAP adapter
  as done.
- `.env.example` documents `CHAOSHIRE_DB_BACKEND`,
  `CHAOSHIRE_DATABASE_URL`, `CHAOSHIRE_LOG_WEBHOOK_URL` and
  `CHAOSHIRE_LOG_WEBHOOK_SECRET`.
- `/api/meta` serves `log_shipping` and `build.repository_backend`.
- The service worker precaches `/static/chaoshire.css`.

### Not faked

- **No paid Redis/Postgres.** The Postgres adapter is real code that
  requires a live `DATABASE_URL` — the free-tier Render deployment still
  uses SQLite, `CHAOSHIRE_AUDIT_HISTORY_DURABLE` stays `0`, and `render.yaml`
  still has no `disk:`.
- **No `control.py` commit, no Blueprint adoption, no history rewrite.**
- **No tags created.** `v0.24.0` tag is left for the owner.
- **Scores preserved.** `audit(legacy)` → **32/F**, `run_chaos_suite("legacy")`
  → **30/100** (gender **169**, community **111**).

### Verified

- `python -m pytest -q` → **265 passed, 5 skipped** (270 collected);
<<<<<<< HEAD
  `--cov=chaoshire` → **94.7%** (90% gate); `ruff format --check` +
=======
  `--cov=chaoshire` → **94.7%** (90% gate); `ruff format --check` +
>>>>>>> ce80706 (fix(ci): correct coverage figure to 94.7% and add ±0.1% tolerance to build_info check)
  `ruff check` → clean; `python scripts/check_build_info.py` → `build_info OK`.

## [0.23.4] - 2026-09-21

Finishes the red-flag 1–40 items still visible on the v0.23.3 live deployment:
the sensational Chaos Lab story blurbs, an unlabelled privilege-injection PASS,
the “Fairness Review Agent” branding, the stale TalentFit blurb, and the
unredacted `GET /api/appeals` queue. The published demo scores are preserved —
LegacyCorp **32/F** with resilience **30/100** (169 gender, 111 community
flips) — and owner-only work is **not** faked (see “Not faked”). Historical
`CHANGELOG.md`/`TODO.md` records keep the original “Fairness Review Agent”
feature name; nothing here rewrites history.

### Fixed

- **Chaos stories no longer read as marketing narrative.** The five `ChaosTest.story` blurbs (“Does the model get gamed?”, “Who survives?”, “A fair model must not change a single decision”) now describe the mechanical experiment — transform, re-score, count of decisions crossing the accept threshold. The gap-stress and age-stress observation `detail` strings (“Disproportionately impacts returning parents and caregivers.”, “Detects hidden ageism in ranking features.”) now state what the test measures (decision flips) and what it does not (intent, disparate treatment, age discrimination). Verdicts, thresholds, evidence and the resilience score are untouched. (`tests/test_review_honesty.py`)
- **The privilege-injection PASS is labelled.** `ChaosTest` gained a `fixture_limit` scope note — populated for Privilege-Keyword Injection only — that ships in every `/api/chaos` result and renders in the Chaos Lab as a **fixture-limited** chip next to the verdict plus a visible scope note: the PASS records that the shipped fixtures cannot accept the injected résumés (exact headroom stays in `detail`), not general résumé-gaming resistance; a prestige-heavy fixture is regression-proven to FAIL (`tests/test_verification_fixes.py`). The label changes no verdict and no resilience point (LegacyCorp stays 30/100). `docs/CONTINUOUS-FAIRNESS.md` and the README say the same. (`tests/test_review_honesty.py`)
- **“Fairness Review Agent” is no longer the product name of a rules engine.** The review payload’s `agent.name` is now `ChaosHire Fairness Review (deterministic rules)` and its `limitations` open with “produced by deterministic rules, not an AI agent or language model”; the dashboard tab is **Fairness Review** with a plain disclosure; guided-demo step 4 is “Run the deterministic fairness review”; the CLI help, README and `docs/PORTFOLIO-PLATFORM.md` say rules engine. `POST /api/agent/review` keeps its route for backward compatibility, and `external_ai: false` was already honest — the *name* was not. (`tests/test_review_honesty.py`, `tests/test_portfolio_platform.py`)
- **The TalentFit blurb reports the measured result** instead of ending on a teaser (“Blind training — but blind decisions?”): “Counterfactual resilience 100/100 — yet 66/C, failing the four-fifths rule (disparate impact 0.78): blind training did not make blind decisions.” (`tests/test_review_honesty.py`)

### Security

- **`GET /api/appeals` serves redacted copies.** New `chaoshire/redaction.py` masks candidate names to initials and replaces emails, bare 7+ digit runs and phone-like runs in messages with `[email redacted]`, `[number redacted]` and `[phone redacted]` on the read path; the response carries a `redaction` block that discloses the rules, and the dashboard prints them under the review queue. The stored record keeps the original text in process memory only and is never mutated or persisted. Redaction is mechanical string matching with no claimed PII detection — `tests/test_appeals_redaction.py` pins the rules, including that identifier-free text round-trips unchanged and that the candidate lookup still shows an applicant their own record — and `SECURITY.md`/`docs/PORTFOLIO-PLATFORM.md` document the limits (“synthetic data only” still applies).

### Changed

- Version `0.23.3` → `0.23.4`; `chaoshire/build_info.py` now reports **216 tests and 98.4%** package coverage (derived + `scripts/check_build_info.py` verified), and `README.md`/`docs/PORTFOLIO-CASE-STUDY.md`/`docs/PORTFOLIO-EVIDENCE.md` quote the same figures.
- `PROJECT-ROADMAP.md` records the current tag state (v0.23.3 tagged by the owner; v0.22.0, v0.23.1, v0.23.2 and v0.23.4 pending owner).

### Not faked (owner-only, documented as limitations)

- **Tags.** `v0.20.0`, `v0.20.1`, `v0.21.0`, `v0.23.0` and `v0.23.3` (owner, on `4447fe1`) are tagged; `v0.22.0`, `v0.23.1` and `v0.23.2` remain untagged; **no `v0.23.4` tag is created in this branch** and `TODO.md`/`PROJECT-ROADMAP.md` do not pretend otherwise.
- **UptimeRobot.** Monitor configuration lives in the owner's UptimeRobot account (`docs/MONITORING.md`). No synthetic monitor is fabricated and the Render cold-start notice is kept.
- **CodeQL UI dismissal.** The one accepted `py/clear-text-storage-sensitive-data` false positive on `chaoshire train --include-protected` stays dismissed **only** in the code-scanning UI with reasoning in `SECURITY.md` → Static analysis. No inline suppression comment is added and no repo-wide query exclusion is used.
- **Durability.** `render.yaml` stays on `plan: free` with **no** `disk:` entry; `CHAOSHIRE_AUDIT_HISTORY_DURABLE` stays `0`; paid Redis/Postgres is not pretended; ephemeral storage remains documented in `SECURITY.md`/`docs/MONITORING.md`/`docs/PERSISTENCE.md`.
- **Scores preserved.** `audit(legacy)` remains **32/F** and `run_chaos_suite("legacy")` remains **30/100** (gender flips **169**, community flips **111**) — `chaoshire/models.py`, `chaoshire/metrics.py` and every experiment computation are unchanged (only story/detail wording and an added `fixture_limit` field). (`tests/test_trained_model.py`, `tests/test_verification_fixes.py`, `tests/test_review_honesty.py`)
- **History and hygiene.** No merge, no history rewrite, no `disk:` addition, no `control.py` commit (`.gitignore` covers `data/*.db`, `reports/generated/`; `control.py` is explicitly not tracked).

### Verified

- `python -m pytest -q` → **216 passed**; `python -m pytest --cov=chaoshire` → **98.4%** (90% gate); `ruff format --check` + `ruff check` → clean; `python -m mypy --python-version 3.11/3.12` → clean; `python scripts/check_build_info.py --coverage-json coverage.json` → `build_info OK`.
- Local `uvicorn` smoke: `GET /api/appeals` redacts names/messages and discloses the rules; `GET /api/chaos` carries `fixture_limit` on the labelled PASS; `POST /api/agent/review` names the rules engine and reports `external_ai: false`; `GET /api/meta` serves the measured TalentFit blurb; `HEAD /` → `200`.

## [0.23.3] - 2026-09-21

Continues the v0.23.3 red-flag 1–40 review. The two commits `0ad1125`/`4a4ba98` from the previous sandbox (based on `ce2c4f0`) were not pushed and cannot be cherry-picked onto `cc1636a` (v0.23.2) without conflicts; the remediations below are re-applied on current `main`. Owner-only work (tags, UptimeRobot, CodeQL UI dismissal, paid Redis/Postgres or `disk:`) is **not** faked — see “Not faked” — and the published demo scores are preserved: LegacyCorp **32/F** with resilience **30/100** (`tests/test_trained_model.py`, `tests/test_verification_fixes.py`, `browser_tests/test_landing.py`).

### Fixed

- **Documentation drift: XFF direction.** `chaoshire/platform.py:client_key` has used the left-most `X-Forwarded-For` hop (Render's observed client IP, `:port` stripped) with a process-wide `write:_instance` backstop since v0.23.2, but `docs/PORTFOLIO-PLATFORM.md`, `docs/MONITORING.md`, `SECURITY.md` and `.env.example` still described the right-most entry. All four now say left-most and document the instance cap; `docs/MONITORING.md` also lists `client_ip_selection`, `limiter_scope` and `instance_write_rate_limit_per_minute` in its verify column. (`tests/test_write_access.py::test_forwarded_for_is_only_trusted_when_declared`, `test_whoami_reports_leftmost_xff_when_trusted`, `test_spoofed_leftmost_xff_cannot_escape_the_write_budget`, `test_instance_write_cap_fires_even_when_every_request_has_a_new_ip`, `scripts/probe_xff.py`)
- **Documentation drift: deployment example.** `docs/PORTFOLIO-PLATFORM.md` showed `CHAOSHIRE_RATE_LIMIT_PER_MINUTE=0` (limiter disabled). The example now mirrors the enforced defaults (`120` read, `6` write, `TRUST_FORWARDED_FOR`, `MAX_APPEALS=200`, `ANONYMOUS_APPEALS_PER_MINUTE=2`, `AUDIT_HISTORY_DURABLE=0`).
- **Coverage figure drift.** `CHANGELOG.md` 0.23.2 claimed `98.4%` package coverage; `chaoshire/build_info.py` and CI report `98.3%` (98.32% actual, 90% gate). Corrected here and `docs/PORTFOLIO-EVIDENCE.md` already quotes `201 tests and 98.3%`.
- **Roadmap tag claim.** `PROJECT-ROADMAP.md` claimed tagged releases through v0.23.0 with `v0.22.0 and v0.23.1` pending; `v0.23.2` was missing and the 0.23.2 changelog said the roadmap “no longer claims untagged releases” while still omitting `v0.23.2`. Now `v0.22.0, v0.23.1 and v0.23.2 tags pending owner`.

### Changed

- Version `0.23.2` → `0.23.3`; `chaoshire/build_info.py` still reports **201 tests and 98.3%** (derived + CI-verified) and the landing page renders it via `/api/meta`.
- `.env.example` and `docs/PORTFOLIO-PLATFORM.md` now expose every `render.yaml` Blueprint variable with its default and the `disk:`-on-`plan: free` prohibition.

### Not faked (owner-only, documented as limitations)

- **Tags.** Releases `v0.20.0`, `v0.20.1`, `v0.21.0` and `v0.23.0` are tagged; `v0.22.0`, `v0.23.1`, `v0.23.2` and `v0.23.3` remain untagged until an owner pushes them. No tag is created in this branch and `TODO.md`/`CHANGELOG.md` do not pretend otherwise.
- **UptimeRobot.** Monitor configuration lives in the owner's UptimeRobot account (`docs/MONITORING.md` → UptimeRobot). No synthetic monitor is fabricated and the Render cold-start notice is kept.
- **CodeQL UI dismissal.** The one accepted `py/clear-text-storage-sensitive-data` false positive on `chaoshire train --include-protected` is dismissed **only** in the code-scanning UI with reasoning in `SECURITY.md` → Static analysis. No `lgtm[...]`/`codeql[...]` suppression comment is added and `.github/codeql-config.yml` is not used to exclude the queries repo-wide.
- **Durability.** `render.yaml` stays on `plan: free` with **no** `disk:` entry; `CHAOSHIRE_AUDIT_HISTORY_DURABLE` stays `0`; `SECURITY.md` and `docs/MONITORING.md` state that SQLite is ephemeral and list the three honest postures (stay ephemeral / managed Postgres / periodic export). Paid Redis/Postgres is not pretended.
- **Scores preserved.** `audit(build_decisions(get_model(\"legacy\")))` remains **32/F** (`27.1/85` measured) and `run_chaos_suite(\"legacy\")` remains **30/100** with gender flips **169** and community flips **111** (`index.html`, `chaoshire/demo.py`, `chaoshire/metrics.py`); `fair` stays **84/B** with **100/100** resilience. No coefficient, threshold, or test is altered to hide bias.
- **History and hygiene.** No merge, no history rewrite, no `disk:` addition, no `control.py` commit (`.gitignore` covers `data/*.db`, `reports/generated/`; `control.py` is explicitly not tracked).

### Verified

- `python -m pytest -q` → **201 passed**; `python -m pytest --cov=chaoshire` → **98.3%** (90% gate); `python -m mypy --python-version 3.11/3.12` → clean; `python scripts/check_build_info.py --coverage-json coverage.json` → `build_info OK`.
- `GET /api/meta` → `build: {version: 0.23.3, automated_tests: 201, package_coverage: 98.3%}`, `platform.disclosed: true` on the demo and correctly redacted when `CHAOSHIRE_DISCLOSE_WRITE_POSTURE=0`.
- `GET /api/ops/posture` + `GET /api/ops/whoami` (operator key) prove left-most XFF and the instance cap; `scripts/probe_xff.py` documents the live check.
- `HEAD /` → `200` (UptimeRobot-friendly) and `HEAD /api/health|/live|/ready` → `200`.

## [0.23.2] - 2026-09-20

Rectifies the twelve drawbacks of the v0.23.1 write-posture disclosure.

### Security

- **Import no longer calls ``logging.basicConfig``.** A last-resort stderr
  handler is attached in the lifespan to the ``chaoshire.app`` logger only
  when no ancestor already has a handler, so embedding hosts keep their
  logging. (`tests/test_write_access.py`)
- **Public ``/api/meta`` is no longer an unconditional recon surface.**
  Budgets, key-presence and bucketing are omitted when
  ``CHAOSHIRE_DISCLOSE_WRITE_POSTURE=0`` (the default on private deployments
  where anonymous writes are off). The public demo still discloses. Full
  posture moves to authenticated ``GET /api/ops/posture``.
- **Write budget has a process-wide backstop.** A 2026-09-20 live probe of
  ``chaoshire.onrender.com`` sent 7 anonymous ``POST /api/appeals`` with
  **no** spoofed headers and got 200 seven times, while ``/api/meta``
  advertised ``write_rate_limit_per_minute: 6`` and ``/api/metrics`` showed
  **zero** 429s. Per-client keys were not collapsing (dual-stack and/or
  unique XFF hops). ``require_write_access`` now also buckets
  ``write:_instance`` at the same number, so the advertised cap is enforced
  even when identity fails. Client IP parsing uses Render's left-most XFF
  hop and strips ``:port``.
- **Boot log uses only literal-producing ternaries** (``"true" if flag else
  "false"``) so CodeQL's clear-text-logging query does not treat an
  env-derived bool as taint. No new dismissal. Tests assert tokens, not the
  whole line, and assert the API key never appears.
- **Anonymous uploads-published is one constant**
  (``ANONYMOUS_UPLOADS_PUBLISHED``) feeding the JSON field, the boot line and
  the note — the previous stray ``False`` literal cannot drift.
- **Anonymous appeals cannot wipe operator-filed ones.** The FIFO evicts the
  oldest anonymous entry first; authenticated appeals are only dropped when
  the queue is all-protected. Anonymous ``POST /api/appeals`` also has its
  own per-client budget (``CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE``, default
  2) on top of the write limiter.
- **``HEAD /`` returns 200.** Uptime monitors that probed the landing page
  with HEAD used to get 405.

### Added

- ``GET /api/ops/posture`` and ``GET /api/ops/whoami`` (operator key required).
- Boot reports ``limiter_scope=process-local-memory``,
  ``audit_history_durable``, ``disclose_write_posture``, ``blueprint_drift``
  (``none``/``present``) and ``worker_count``. A warning is emitted when the
  live env disagrees with the committed ``render.yaml`` contract, when more
  than one worker is configured, and when audit history is undeclared-durable.
- ``CHAOSHIRE_AUDIT_HISTORY_DURABLE`` (default 0) — an honest declaration,
  not a persistence implementation. Render free still cannot keep a disk.
- ``scripts/probe_xff.py``.

### Changed

- Version ``0.23.1`` → ``0.23.2``; ``chaoshire/build_info.py`` reports 201
  automated tests and 98.4% package coverage.
- Roadmap no longer claims tags that do not exist: tagged releases are
  v0.20.0, v0.20.1, v0.21.0 and v0.23.0. v0.22.0 and v0.23.1 remain untagged.

## [0.23.1] - 2026-09-20

The deployment's write posture is now verifiable from the running service
itself, and the Render runbook documents how to verify each environment
variable on the live (hand-managed, free-plan) deployment.

### Added

- **`/api/meta` discloses the proxy and bucketing posture.**
  `platform.trusted_proxy_headers` reports whether
  `CHAOSHIRE_TRUST_FORWARDED_FOR` is set, and
  `platform.rate_limit_bucketing` reports the consequence: `per-client-ip`
  when the proxy is trusted, `shared-per-instance` otherwise. The `note`
  names `CHAOSHIRE_TRUST_FORWARDED_FOR=1` and explains that with the variable
  unset every visitor shares one bucket. (`tests/test_write_access.py`)
- **The service logs its resolved write posture once at boot.**
  `chaoshire 0.23.1 resolved write posture: {...}` is the line an operator
  greps for in the Render log stream: booleans and safe scalars only, never
  the key value. (`tests/test_write_access.py`)
- **`docs/MONITORING.md` gains a Render runbook for the hand-managed
  free-plan service:** `render.yaml` is a Blueprint, not a deploy script; an
  environment-variable table with a live verify method per variable; the local
  key-generation command; the Blueprint-adoption risk (a second service means
  a new URL and every `chaoshire.onrender.com` link breaks); and an "audit
  history is ephemeral on the free plan" section listing the three persistence
  options and warning not to add `disk:` while `plan: free`.

### Verified in production

- `CHAOSHIRE_API_KEY` is set on the live service: a wrong `X-API-Key` gets
  `401`.
- `CHAOSHIRE_TRUST_FORWARDED_FOR=1` is set: `/api/meta` reports
  `trusted_proxy_headers: true` / `per-client-ip`.
- Anonymous uploads answer `200` with `published: false` and no `audit_id`.
- `/api/meta` reports rate limits `120`/`6` and appeals capacity `200`.

### Changed

- Version `0.23.0` → `0.23.1`; `chaoshire/build_info.py` reports 190 automated
  tests (package coverage unchanged at 97.5%).
- Living documentation moved to the v0.23.1 baseline (README, portfolio case
  study, evidence and platform documents, roadmap release range).
- `POST /api/appeals` behaviour is unchanged: public-write, bounded by the
  capped FIFO queue — the cap is the mitigation.

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
- **`train --include-protected` writes its report to a file instead of stdout.**
  The variable was also renamed from `leaked` to `contrast_coefficients` — the fit
  is a synthetic contrast, not a leaked secret, and the old name mislabelled it.
  CodeQL's `py/clear-text-logging` rule classifies *every* value derived from a
  protected-attribute fit as private data reaching an output sink: not just the
  coefficients, but the certificate and the gender disparate impact computed from
  them. That verdict is a false positive here (the fixture is the bundled
  synthetic 1,000-row population and its protected-attribute weights are already
  published in `chaoshire/models.py`), but inline `# codeql[...]` suppression
  comments are not honoured by this repository's code-scanning configuration — the
  alert was re-reported on the `json.dumps` argument, then the enclosing `print`
  call, then a single-line `sys.stdout.write` sink. Rather than disable the query
  repo-wide, which would stop it catching a genuine credential in a log line
  elsewhere, the report now goes to `reports/generated/protected-contrast.json`
  (already in `.gitignore`; override with `--out`) and stdout gets a static
  acknowledgement. Nothing derived from the fit is printed. The file keeps
  everything the flag exists to show: the coefficients, the certificate
  (**48/D**) and the gender disparate impact (**0.678**, worse than the blind
  fit's 0.78, which is the case for blinding). A file is also simply the better
  channel for a machine-readable report. `tests/test_trained_model.py` asserts
  both halves. The `--write` guard that refuses to pin a protected-attribute fit
  is unchanged.

  Changing the sink does not clear the alert: the two clear-text queries share
  one source model, so `py/clear-text-logging-sensitive-data` on the `print`
  became `py/clear-text-storage-sensitive-data` on the `write_text`. CodeQL
  classifies these values as "sensitive data (private)" by *name heuristic*
  (`SensitiveDataSources.qll` matches identifiers and string literals that look
  like credentials or personal data — here `PROTECTED_FEATURES`, `gender_M`,
  `eth_G2`, `age_50+`, `include_protected`), and the taint survives the
  arithmetic into the certificate total and the gender disparate impact, so no
  reduction of the output clears it either. The alert is therefore dismissed as a
  false positive in the code-scanning UI rather than by disabling the queries
  repo-wide; SECURITY.md → "Static analysis" records the full reasoning and the
  condition that voids it (any deployment handling real candidate data).
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
