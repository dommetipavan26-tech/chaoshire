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
| Appeal queue capacity | `200` entries, FIFO with eviction | `CHAOSHIRE_MAX_APPEALS` |
| Trust `X-Forwarded-For` for rate-limit buckets | `0` (`1` on Render, behind its proxy) | `CHAOSHIRE_TRUST_FORWARDED_FOR` |

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

`GET /api/meta` returns the resolved posture as `platform`, so a reviewer can
see what a given deployment actually enforces instead of trusting this file.
`tests/test_write_access.py` covers all of the above.

## Content security

- Responses carry a per-request **nonce-based Content-Security-Policy**:
  `default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'
  'nonce-…'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';
  base-uri 'self'; form-action 'self'`. There is no `script-src 'unsafe-inline'`
  and the nonce is regenerated per request, so a leaked page cannot be replayed.
- `index.html` contains exactly one `<script>` tag, carries no inline event
  handlers, and builds no HTML by unescaped string concatenation. Its `esc()`
  helper escapes `& < > " '` and the backtick. Every interpolation into an
  attribute that can break out (`href`, `src`, `value`, `title`, `alt`,
  `placeholder`, `id`, `for`, `name`, `data-*`) goes through `esc()` or
  `encodeURIComponent()`; the remaining `class`/`style`/`aria-*` interpolations
  are a frozen, reviewed presentational allowlist.
  `tests/test_html_escaping.py` asserts the invariant mechanically and includes a
  regression test that uploads a hostile group value containing
  `" onerror="…` and confirms it renders as inert text.
- Server-rendered HTML and PDF reports escape through `html.escape(quote=True)`
  and a PDF string escaper that neutralises `\`, `(` and `)`.
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
  every response that mentions it. `tests/test_threshold_contrast.py`.
- **The fairness risk score is measured, not padded.**
  `total = measured / available × 100`. Earlier versions added an unconditional
  15 "transparency" points that were never measured and capped a perfect result
  at 85. The denominator switches between 85 (ground-truth qualification labels
  present) and 60 (not), and that switch is disclosed through `basis`,
  `available_points`, `unmeasured_components` and `comparable_with_full_basis`
  rather than hidden behind two identical-looking numbers.
  `tests/test_certificate_scale.py`.

## Current limitations

- Raw uploaded CSV rows and appeals are stored in process memory; both are bounded (request-size cap and a 200-entry appeal queue) but neither survives a restart.
- Named aggregate audit results and interpretation settings are stored in SQLite; raw candidate rows and IDs are not written to history.
- Render free-tier storage is ephemeral and must not be treated as a durable record system.
- There are no user accounts and no role-based authorization. Write access is a single shared operator key; anyone holding it can publish.
- Aggregate history remains readable to visitors when the portfolio demo is operated publicly.
- The demo keeps a single shared upload slot for *published* uploads: `/api/audit?dataset=uploaded`, `/api/audit/export`, `/api/evidence?dataset=uploaded`, and the uploaded report endpoints return the most recent authenticated upload made by anyone. Only aggregate metrics and interpretation settings are exposed, and the slot is swapped under a lock so concurrent uploads cannot interleave.
- Rate limits are per resolved client IP. Behind a proxy without `CHAOSHIRE_TRUST_FORWARDED_FOR=1` every visitor shares one bucket; with it enabled only the right-most `X-Forwarded-For` entry is used, so a client cannot rotate the header to evade the limit.
- Responses include request IDs, security headers, a nonce-based content policy, request-size enforcement, and rate limiting; these controls have not undergone an independent security assessment.
- The application has not undergone an independent security or privacy assessment.
- The demonstration is not designed for sensitive production workloads.

## Reporting a vulnerability

Please report security issues privately to the repository owner rather than opening a public issue containing exploitation details or sensitive information. Include affected component, reproduction steps, likely impact, and a suggested fix if available.

Production adoption would require authentication, authorization, encryption, secure storage, retention controls, audit logging, dependency scanning, privacy review, and legal review.
