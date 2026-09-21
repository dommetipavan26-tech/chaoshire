# Free deployment monitoring

## Render

The production service is `https://chaoshire.onrender.com`, a Docker web service on the free plan. Health check: `/api/ready`. Liveness: `/api/live`. Operational snapshot: `/api/metrics`.

### Runbook for the hand-managed service

The live service was created by hand in the Render dashboard. `render.yaml` is
a **Blueprint, not a deploy script**: it is not synced to the existing service,
and the environment variables below are set and changed on the service's
dashboard page, not by applying the file. Every variable in the table has a
live verify method so the deployed posture can be confirmed without trusting
the dashboard.

| Variable | Live value | What it does | How to verify it took effect |
|---|---|---|---|
| `CHAOSHIRE_API_KEY` | generated at deploy time | Holding it is what makes an upload *published* | `GET /api/meta` → `platform.api_key_configured: true` (when disclosure is on); a request with a wrong `X-API-Key` gets `401`. The value is never logged or echoed. |
| `CHAOSHIRE_ALLOW_ANONYMOUS_WRITES` | `1` | Keeps the public demo interactive | Anonymous `POST /api/upload` → `200` with `published: false` and no `audit_id` |
| `CHAOSHIRE_RATE_LIMIT_PER_MINUTE` | `120` | Per-client read budget | `GET /api/meta` → `platform.rate_limit_per_minute: 120` |
| `CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE` | `6` | Per-client write budget | `GET /api/meta` → `platform.write_rate_limit_per_minute: 6`; a 7th mutating call within a minute gets `429` |
| `CHAOSHIRE_TRUST_FORWARDED_FOR` | `1` | Buckets limits by the left-most `X-Forwarded-For` entry (Render's client IP, `:port` stripped) plus a process-wide `write:_instance` backstop at the same budget | Config: `/api/meta` → `trusted_proxy_headers: true` / `client_ip_selection: left-most-x-forwarded-for`, `limiter_scope: process-local-memory`, `instance_write_rate_limit_per_minute: 6`. Behaviour: `GET /api/ops/whoami` with a spoofed left-most XFF, or `python scripts/probe_xff.py --host chaoshire.onrender.com --limit 6` (rotating left-most still hits 429 via the instance cap) |
| `CHAOSHIRE_MAX_APPEALS` | `200` | Caps the appeal FIFO; anonymous evicted first | `GET /api/meta` → `platform.appeals_capacity: 200` |
| `CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE` | `2` | Extra anonymous-appeal budget | A 3rd anonymous `POST /api/appeals` within a minute gets `429`; authenticated appeals are unaffected |
| `CHAOSHIRE_AUDIT_HISTORY_DURABLE` | `0` | Honest declaration, not a disk | Boot log `audit_history_durable=false`; `/api/meta` → `platform.audit_history_durable: false` |
| `CHAOSHIRE_DB_PATH` | `/app/data/chaoshire.db` | Where the aggregate-history SQLite file lives | `GET /api/ready` → `{"status": "ready", "database": "available"}` |
| `CHAOSHIRE_MAX_BODY_BYTES` | `5500000` | Rejects over-long request bodies | A POST with a larger `Content-Length` gets `413` |

On the public demo, `GET /api/meta` still discloses the posture. Private
deployments set `CHAOSHIRE_DISCLOSE_WRITE_POSTURE=0` and read the same facts
from authenticated `GET /api/ops/posture`. The service logs a key=value summary
once at boot (`chaoshire <version> resolved write posture: …`) — string
literals `true`/`false`, never the key value. `blueprint_drift=present` means
the live env disagrees with the committed `render.yaml` contract (dashboard vs
Blueprint). `HEAD /` returns 200 so an uptime monitor on the landing page no
longer records 405.

To generate a key locally (for example when rotating the deployment's key in
the dashboard):

```bash
python -c "import secrets;print(secrets.token_urlsafe(32))"
```

#### Why not just apply the Blueprint?

Adopting `render.yaml` would have Render provision the service it describes —
the existing hand-created service is not the Blueprint's service, so adoption
means a **second service with a new URL**, and every existing
`chaoshire.onrender.com` link breaks: the README, the portfolio evidence
documents, UptimeRobot's monitors, and every previously shared URL. Keeping
both would also mean two free instances, each with its own cold start and its
own copy of the bounded in-memory state. Until an owner decision says
otherwise, the hand-managed service stays and its dashboard page — not the
file — is the source of truth for its environment.

#### Audit history is ephemeral on the free plan

Render's free filesystem is wiped on redeploy, instance replacement, and
platform maintenance, so the SQLite audit history (`GET /api/audits`) is
**ephemeral**: it survives a process restart on the same instance and nothing
more. `docs/PERSISTENCE.md` defines what is stored; this section is about how
long it lasts. Three postures are on the table:

1. **Stay ephemeral.** Accept that the history is demo scratch space, keep the
   "not durable cloud storage" wording, and do nothing. Cheapest, and honest.
2. **External managed store.** Point the repository at a managed database
   (Render Postgres or an equivalent) through the planned repository adapter so
   history survives redeploys. Costs money and adds a second service with its
   own cold starts.
3. **Ship, don't store.** Export the history periodically (for example
   `GET /api/audit/export` to object storage) instead of making the running
   service own durability.

Whatever is chosen, do **not** add a `disk:` entry to `render.yaml` while
`plan: free` — the free plan has no persistent disks, and the Blueprint would
fail to provision.

## UptimeRobot

1. Create an HTTPS monitor named `ChaosHire production`.
2. URL: `https://chaoshire.onrender.com/api/ready`.
3. Interval: the shortest interval offered by the free plan.
4. Expected status: HTTP 200. ChaosHire accepts both GET and HEAD on `/`, `/api/health`, `/api/live`, and `/api/ready`.
5. Optional keyword monitoring must use GET because HEAD responses do not contain a body.
6. Add an email alert contact and trigger alerts after two failed checks.
7. Create a second monitor for `https://chaoshire.onrender.com/` if desired.

UptimeRobot configuration lives in the owner's account and cannot be proven from this repository. Keep the Render cold-start message even with monitoring because free-tier behavior can change.

## Incident checklist

1. Check `/api/live`; if unavailable, inspect Render events and logs.
2. Check `/api/ready`; if live succeeds but ready fails, inspect database path and permissions.
3. Check `/api/metrics` for 5xx counts and latency; unhandled endpoint exceptions are recorded there as server errors and 500 status counts.
4. Reproduce with the deterministic `/api/demo` workflow.
5. Roll back to the previous successful GitHub commit if necessary.

Metrics are process-local, reset on restart, and contain no candidate data. Do not use query strings or audit payloads in monitoring names or alerts.
