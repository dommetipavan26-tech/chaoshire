# Security and data safety

ChaosHire's public deployment is a demonstration environment. **Do not upload real applicant or employee data.** Use synthetic or properly anonymized records only.

This document describes the posture the shipped configuration actually enforces, not an aspiration. Every claim below is covered by a test in `tests/`; the test name is given where it helps.

## Write access

| Control | Default | Env var |
|---|---|---|
| Operator key for publishing writes | *unset locally, generated at deploy time* | `CHAOSHIRE_API_KEY` |
| Anonymous writes accepted at all | `1` (allowed, but never published) | `CHAOSHIRE_ALLOW_ANONYMOUS_WRITES` |
| Read rate limit | `120`/minute/IP | `CHAOSHIRE_RATE_LIMIT_PER_MINUTE` |
| Write rate limit | `6`/minute/IP | `CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE` |
| Request body cap | `5,500,000` bytes | `CHAOSHIRE_MAX_BODY_BYTES` |
| Appeal queue capacity | `200` entries, FIFO; anonymous evicted first | `CHAOSHIRE_MAX_APPEALS` |
| Anonymous appeal budget | `2`/minute/IP, on top of the write budget | `CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE` |
| Trust `X-Forwarded-For` for rate-limit buckets | `0` (`1` on Render, behind its proxy) | `CHAOSHIRE_TRUST_FORWARDED_FOR` |
| Disclose budgets on `/api/meta` | follows anonymous-writes; set `0` in production | `CHAOSHIRE_DISCLOSE_WRITE_POSTURE` |
| Audit history declared durable | `0` (honest for Render free) | `CHAOSHIRE_AUDIT_HISTORY_DURABLE` |

`render.yaml` sets `CHAOSHIRE_API_KEY` with `generateValue: true`, so a public
deploy gets a real secret rather than an unset one, and sets every rate limit to
a non-zero value.

**Holding the key is what makes an upload *published*.** An authenticated upload
is written to the persistent audit history, receives an `AUD-*` identifier, and
becomes the shared `dataset=uploaded` artifact. An anonymous upload is audited,
returned to the caller, and discarded: `published: false`, `audit_id: null`, and
it never appears in `/api/audits` or the shared slot. That is what closes the
defacement path — previously any visitor could write an attacker-chosen audit
name into the history every other visitor reads — without removing the
interactive demo. Audit names are additionally normalised by
`sanitise_audit_name()`: control characters become spaces, whitespace runs
collapse, and the result is capped at 60 characters.

The gateway fails closed. With anonymous writes disabled and no key configured
it answers `503` rather than silently accepting writes, which is what the old
no-op configuration did.

`GET /api/meta` returns the resolved posture as `platform` **when disclosure is
on** (the public demo). Private deployments set
`CHAOSHIRE_DISCLOSE_WRITE_POSTURE=0` and the same facts move to authenticated
`GET /api/ops/posture`. `GET /api/ops/whoami` returns the rate-limit bucket key
for the current request so the left-most-XFF rule and the instance-wide
`write:_instance` backstop can be proved against the live proxy, not just read
as a config flag. `scripts/probe_xff.py` automates that probe.
`tests/api/test_write_access.py` covers all of the above.

## Content security

- Responses carry a per-request **nonce-based Content-Security-Policy**:
  `default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'
  'nonce-…'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';
  base-uri 'self'; form-action 'self'`. There is no `script-src 'unsafe-inline'`
  and the nonce is regenerated per request, so a leaked page cannot be replayed.
- `chaoshire/web/index.html` contains exactly one `<script>` tag, carries no inline event
  handlers, and builds no HTML by unescaped string concatenation. Its `esc()`
  helper escapes `& < > " '` and the backtick. Every interpolation into an
  attribute that can break out (`href`, `src`, `value`, `title`, `alt`,
  `placeholder`, `id`, `for`, `name`, `data-*`) goes through `esc()` or
  `encodeURIComponent()`; the remaining `class`/`style`/`aria-*` interpolations
  are a frozen, reviewed presentational allowlist.
  `tests/web/test_html_escaping.py` asserts the invariant mechanically and includes a
  regression test that uploads a hostile group value containing
  `" onerror="…` and confirms it renders as inert text.
- Server-rendered HTML and PDF reports escape through `html.escape(quote=True)`
  and a PDF string escaper that neutralises `\`, `(` and `)`.
- **Exception text never reaches a response body.** Remote-connector failures
  return `502` with the failure category and the exception *class* as `reason`;
  CSV parse failures return `422` with `(ParserError)`-style class names. Upstream
  exceptions routinely embed the request URL, proxy configuration or a credential
  fragment, and pandas parser messages can quote buffer contents, so the full text
  is written to the server log instead, where an operator can still read it.
  `tests/infrastructure/test_security_connectors.py` asserts that a connector exception carrying
  `https://operator:sk-live-SUPERSECRET@…?token=abc123` produces a body containing
  none of those fragments while the log contains all of them.
- `style-src 'unsafe-inline'` is still permitted. Inline `style` attributes are
  used for layout; CSS injection is not script execution, and removing it would
  require moving the whole stylesheet out of line for no security gain. This is a
  deliberate, documented trade-off rather than an oversight.

## Fairness-specific controls

- **Per-group threshold calibration is not offered as a mitigation.** Setting
  different cutoff scores by race, colour, religion, sex or national origin in an
  employment test is an unlawful employment practice under
  [42 U.S.C. § 2000e-2(l)](https://www.law.cornell.edu/uscode/text/42/2000e-2)
  (Civil Rights Act of 1991). `mitigate(["calibrate"])` is rejected at the schema
  level with HTTP 422. The computation still exists as a labelled research
  contrast, reachable only with `threshold_contrast_acknowledged: true`, reported
  under its own `research_contrast` key, never merged into a mitigation result,
  and accompanied by the statute, its text and a "not legal advice" notice in
  every response that mentions it. `tests/core/test_threshold_contrast.py`.
- **The fairness risk score is measured, not padded.**
  `total = measured / available × 100`. Earlier versions added an unconditional
  15 "transparency" points that were never measured and capped a perfect result
  at 85. The denominator switches between 85 (ground-truth qualification labels
  present) and 60 (not), and that switch is disclosed through `basis`,
  `available_points`, `unmeasured_components` and `comparable_with_full_basis`
  rather than hidden behind two identical-looking numbers.
  `tests/core/test_certificate_scale.py`.

## Static analysis

CodeQL runs on every push and pull request (`.github/workflows/security.yml`,
plus the repository's code-scanning results check). One accepted deviation is
recorded here because it is a deliberate design decision rather than an oversight:

- `py/clear-text-storage-sensitive-data` (CWE-312) and its sibling
  `py/clear-text-logging-sensitive-data` fire on `chaoshire train
  --include-protected`, which reports a contrast fit trained *with* protected
  attributes. **The alert is dismissed as a false positive in the code-scanning
  UI**; the reasoning is recorded here so the dismissal can be re-audited.

  CodeQL classifies these values as "sensitive data (private)" by *name
  heuristics* — `semmle/python/dataflow/new/SensitiveDataSources.qll` matches
  identifiers, string literals, attribute names and parameter names that look
  like credentials or personal data. This project's vocabulary is protected
  attributes (`PROTECTED_FEATURES`, `gender_M`, `eth_G2`, `age_50+`,
  `include_protected`), so every value downstream of the contrast fit inherits
  the taint — including the certificate total and the gender disparate impact,
  which are computed from it by arithmetic. Two consequences follow. First, the
  verdict cannot be avoided by reducing what is emitted: trimming the raw
  coefficients left the certificate and the impact ratio flagged. Second, it
  cannot be avoided by changing the sink: moving the report from `print` to a
  file simply swapped the logging query for the storage query, because both
  share the same source model.

  It is a false positive on the merits. The fixture is the bundled synthetic
  1,000-row population, no real candidate data exists in this repository or in
  any deployment of it, and the same protected-attribute weights are already
  published as constants in `chaoshire/models.py`. The CWE-312 threat model —
  clear-text exposure of credentials or personal data on storage a third party
  can read — does not describe a report the operator asked for, in their own
  working directory, under `reports/generated/`, which `.gitignore` excludes.

  Inline `# codeql[...]` suppression comments are not honoured by this
  repository's code-scanning configuration (verified across four revisions of
  the sink: the `json.dumps` argument, the enclosing `print`, a single-line
  `sys.stdout.write`, and the `write_text` call). Excluding the two queries via
  `.github/codeql-config.yml` was considered and rejected: it would stop them
  catching a genuine "password written to a log" or "secret persisted to disk"
  bug anywhere else in the package. Dismissing this one alert is the narrower
  action, and it is the disposition GitHub's own guidance recommends for a
  genuine false positive.

  The CLI still writes the whole report to
  `reports/generated/protected-contrast.json` (`--out` overrides the path) and
  prints only a static acknowledgement, which is the better channel for a
  machine-readable report regardless of the scanner; `tests/core/test_trained_model.py`
  enforces both halves. **Re-review this dismissal — and never rely on it — before
  any deployment that handles real candidate data.**

## Current limitations

- Raw uploaded CSV rows and appeals are stored in process memory; both are bounded (request-size cap and a 200-entry appeal queue) but neither survives a restart. `GET /api/appeals` serves **redacted copies** only — names masked to initials; emails, bare 7+ digit runs and phone-like runs replaced with `[email redacted]`, `[number redacted]` and `[phone redacted]` — and discloses the rules in the response (`chaoshire/redaction.py`). Redaction is mechanical string matching and can miss novel identifier formats; the "synthetic data only" rule for the public demo still applies.
- Named aggregate audit results and interpretation settings are stored in SQLite; raw candidate rows and IDs are not written to history.
- Render free-tier storage is ephemeral and must not be treated as a durable record system.
- There are no user accounts and no role-based authorization. Write access is a single shared operator key; anyone holding it can publish.
- Aggregate history remains readable to visitors when the portfolio demo is operated publicly.
- The demo keeps a single shared upload slot for *published* uploads: `/api/audit?dataset=uploaded`, `/api/audit/export`, `/api/evidence?dataset=uploaded`, and the uploaded report endpoints return the most recent authenticated upload made by anyone. Only aggregate metrics and interpretation settings are exposed, and the slot is swapped under a lock so concurrent uploads cannot interleave.
- Rate limits are per resolved client IP and **process-local memory**: they reset on restart and they double if the process is replicated. Behind a proxy without `CHAOSHIRE_TRUST_FORWARDED_FOR=1` every visitor shares one bucket; with it enabled only the left-most `X-Forwarded-For` entry (the client IP Render observed, with any `:port` stripped) is used, and a process-wide `write:_instance` bucket at the same write budget enforces the advertised cap even when per-client keys diverge. A client still cannot rotate the header to evade the limit, and the backstop proves it even when identity fails — verify with `GET /api/ops/whoami` or `scripts/probe_xff.py`.
- `/api/meta` is a recon surface when disclosure is on. Turn it off
  (`CHAOSHIRE_DISCLOSE_WRITE_POSTURE=0`) before hosting real data.
- Anonymous `POST /api/appeals` is still public-write on the demo, but
  anonymous entries are evicted before authenticated ones and have a tighter
  per-client budget.
- Responses include request IDs, security headers, a nonce-based content policy, request-size enforcement, and rate limiting; these controls have not undergone an independent security assessment.
- The application has not undergone an independent security or privacy assessment.
- The demonstration is not designed for sensitive production workloads.

## Reporting a vulnerability

Please report security issues privately to the repository owner rather than opening a public issue containing exploitation details or sensitive information. Include affected component, reproduction steps, likely impact, and a suggested fix if available.

Production adoption would require authentication, authorization, encryption, secure storage, retention controls, audit logging, dependency scanning, privacy review, and legal review.
