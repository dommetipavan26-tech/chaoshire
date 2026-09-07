# Free deployment monitoring

## Render

Deploy from `render.yaml` or keep the existing Docker web service. Health check: `/api/ready`. Liveness: `/api/live`. Operational snapshot: `/api/metrics`. Configure `CHAOSHIRE_API_KEY` as a secret if public writes should be restricted.

## UptimeRobot

1. Create an HTTPS monitor named `ChaosHire production`.
2. URL: `https://chaoshire.onrender.com/api/ready`.
3. Interval: the shortest interval offered by the free plan.
4. Expected status: HTTP 200; optional keyword: `ready`.
5. Add an email alert contact and trigger alerts after two failed checks.
6. Create a second monitor for `https://chaoshire.onrender.com/` if desired.

UptimeRobot configuration lives in the owner's account and cannot be proven from this repository. Keep the Render cold-start message even with monitoring because free-tier behavior can change.

## Incident checklist

1. Check `/api/live`; if unavailable, inspect Render events and logs.
2. Check `/api/ready`; if live succeeds but ready fails, inspect database path and permissions.
3. Check `/api/metrics` for 5xx counts and latency.
4. Reproduce with the deterministic `/api/demo` workflow.
5. Roll back to the previous successful GitHub commit if necessary.

Metrics are process-local, reset on restart, and contain no candidate data. Do not use query strings or audit payloads in monitoring names or alerts.
