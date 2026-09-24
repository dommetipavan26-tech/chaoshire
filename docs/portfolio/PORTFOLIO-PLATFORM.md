# Portfolio platform engineering (Days 11–20)

ChaosHire is a standalone open-source portfolio project. Its core does not depend on a cloud vendor or external AI service.

## Fairness review (deterministic rules)

`POST /api/agent/review` runs a deterministic, evidence-grounded review — a transparent rules engine, not an AI agent or language model. It ranks fairness risk-score, primary-attribute, intersectional, and Chaos findings; links every finding to an evidence path; and returns a human-action plan. It does not invent facts or send audit data to an external model. (Earlier releases branded this the "Fairness Review Agent"; the name overclaimed what it is. The `/api/agent/review` route is kept for backward compatibility.)

```json
{"model":"legacy","dataset":"demo","include_chaos":true}
```

The review is decision support, not legal advice. `python -m chaoshire review --model legacy` provides the same workflow from the command line.

## Model adapters

`DecisionAdapter` is the integration boundary for model versions. An adapter describes itself and returns a normalized pandas decision frame. The built-in reference adapter, configurable CSV adapter, callable provider, and authenticated remote HTTP connector are documented by `GET /api/adapters`. Uploaded code is never executed.

## Remote model connector

Set `CHAOSHIRE_REMOTE_MODELS` to a JSON list of connector objects
(`model_id`, `url`, optional `api_key_env` and `timeout_seconds`) to register
authenticated HTTP decision sources. `POST /api/connectors/audit`
(`{"model_id": "..."}`, write-access guarded) fetches the decisions,
normalises `accepted` (bool/int/string), and runs the standard fairness audit;
upstream or credential problems answer 502, unknown connectors 404.
`GET /api/adapters` lists configured connector ids without ever exposing
credentials. URLs come only from operator configuration, never from request
input, so the public API gains no SSRF surface.

## Optional write protection

Set `CHAOSHIRE_API_KEY` to protect CSV uploads and appeal submissions. Clients then send the key in `X-API-Key`. If the variable is absent, the portfolio demo remains open and backward compatible. Never commit the key.

## Platform protections

All responses receive a request ID, content-sniffing protection, frame denial, a restrictive permissions policy, referrer protection, and a same-origin Content Security Policy whose `script-src` uses a per-request nonce instead of `'unsafe-inline'` (plus `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`). `CHAOSHIRE_MAX_BODY_BYTES` defaults to 5,500,000. Fixed-window rate limiting is on by default (`CHAOSHIRE_RATE_LIMIT_PER_MINUTE=120`, `CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE=6`); setting either to zero disables that limiter, and `render.yaml` deliberately does not. Behind a trusted proxy, `CHAOSHIRE_TRUST_FORWARDED_FOR=1` buckets limits by the left-most `X-Forwarded-For` entry (the client IP Render observed, with any `:port` stripped) so a client cannot rotate the header; a process-wide `write:_instance` bucket at the same write budget enforces the advertised cap even when per-client keys diverge. Writes are gated by `CHAOSHIRE_API_KEY` — which `render.yaml` generates at deploy time — and only authenticated uploads are published to the shared history; anonymous uploads are audited, returned to the caller, and discarded. The appeal queue is a bounded FIFO (`CHAOSHIRE_MAX_APPEALS=200`) that evicts anonymous entries before authenticated ones; anonymous appeals also have a per-client budget (`CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE=2`). `GET /api/appeals` is unauthenticated (it feeds the demo's HR review queue), so it serves **redacted copies** of every record — names masked to initials; emails, bare 7+ digit runs and phone-like runs replaced with `[email redacted]`, `[number redacted]` and `[phone redacted]` — and discloses the rules in the same payload (`chaoshire/redaction.py`). The originals stay in process memory and are never persisted. `GET /api/meta` reports the resolved posture as `platform` when disclosure is on; private deployments redact budgets and expose them on authenticated `GET /api/ops/posture`. `GET /api/ops/whoami` proves the left-most-XFF rule and the instance backstop against the live proxy. The service logs the same summary once at boot (literal `true`/`false`, never the key value) and warns on Blueprint drift, multiple workers, or undeclared-durable storage.

## Operations

- `GET /api/live` — process liveness
- `GET /api/ready` — verifies the aggregate repository can initialize
- `GET /api/metrics` — uptime, requests, server errors, status counts, and average duration
- `X-Request-ID` — accepts a caller ID or generates one for correlation

Metrics reset whenever the process restarts and contain no candidate data.

## Tamper-evident evidence

`GET /api/evidence` combines aggregate audit evidence, Chaos results, and the deterministic fairness review in `chaoshire.evidence.v1`. A SHA-256 digest covers canonical JSON. `POST /api/evidence/verify` detects any later modification. This proves integrity relative to the downloaded bundle; it is not a third-party digital signature.

CLI equivalent:

```bash
python -m chaoshire evidence --model legacy --output evidence.json
```

## Native PDF

`GET /api/report.pdf` generates a dependency-free PDF summary with the fairness risk score, group metrics, intersections, Chaos outcomes, experiment ID, and limitations. HTML remains the richer report format.

```bash
python -m chaoshire report --model legacy --format pdf --output report.pdf
```

## Mobile, accessibility, and PWA shell

The dashboard has a skip link, visible keyboard focus, reduced-motion handling, responsive single-column layouts, 44-pixel mobile controls, scroll-safe tables, live loading regions, a web manifest, and a small service worker. The worker caches only the application shell; API evidence remains network-first and is not placed in the offline cache.

## Guided demonstration

`GET /api/demo` returns a stable six-step, three-minute portfolio story covering baseline risk, controlled Chaos, candidate C-1046, fairness review, mitigation/comparison, and the release decision. The dashboard exposes the same story in the Guided Demo tab.

## Deployment environment

```text
CHAOSHIRE_DB_PATH=data/chaoshire.db
CHAOSHIRE_API_KEY=optional-secret  # generate: python -c "import secrets;print(secrets.token_urlsafe(32))"
CHAOSHIRE_ALLOW_ANONYMOUS_WRITES=1
CHAOSHIRE_RATE_LIMIT_PER_MINUTE=120
CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE=6
CHAOSHIRE_TRUST_FORWARDED_FOR=0  # 1 behind Render/nginx
CHAOSHIRE_MAX_APPEALS=200
CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE=2
CHAOSHIRE_AUDIT_HISTORY_DURABLE=0  # honest for Render free; no disk: on plan: free
CHAOSHIRE_MAX_BODY_BYTES=5500000
CHAOSHIRE_REMOTE_MODELS=[{"model_id":"acme-v4","url":"https://models.example/decisions","api_key_env":"ACME_KEY"}]
```

SQLite remains the default. Render free-tier files are ephemeral; use the optional PostgreSQL repository adapter with a managed database for durable aggregate history. Multi-instance deployments also need shared state and rate limiting, which are not provided by the process-local demo.
