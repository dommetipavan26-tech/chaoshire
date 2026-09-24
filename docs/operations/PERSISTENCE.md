# Audit-history persistence and privacy

ChaosHire stores aggregate audit evidence in SQLite by default. This document defines what is and is not persisted.

## Persisted

For each successful uploaded audit, ChaosHire saves:

- Random audit ID
- User-provided audit name
- UTC creation time
- Source type
- Candidate and accepted counts
- Protected-attribute names
- Audit interpretation configuration
- Aggregate group metrics and confidence intervals
- Intersectional metrics
- Fairness risk score and grade

## Not persisted

ChaosHire deliberately does not write the following upload contents to SQLite:

- Candidate IDs
- Candidate names
- Individual decisions
- Individual qualification labels
- Complete uploaded rows
- Original CSV text

The raw parsed DataFrame remains in process memory only so the current session can render and export its aggregate audit. A restart clears those rows.

The public demonstration has no visitor authentication. Audit names, aggregate metrics, and configurations returned by the history API are visible to every visitor. Use synthetic data and non-sensitive audit names only.

## Site preferences and anonymous analytics

The browser uses `localStorage` to remember an explicit analytics Allow or Reject choice. No tracking cookies or third-party analytics scripts are loaded. Only after Allow does the browser send an allowlisted page-section name to `POST /api/analytics/view`; it sends no visitor ID, name, candidate ID, or referrer. Daily aggregate counters are held in process memory for at most 30 UTC days, reset on restart, and can be read only through operator-authenticated `GET /api/ops/analytics`. Separate short-term rate-limit buckets do keep client IP identifiers in memory until a process restart; they are not copied into the analytics counters. Hosting-provider access logs may have their own retention.

See the [Privacy Policy source](../../chaoshire/web/privacy.html) for the visitor-facing notice (served at `/privacy` after deployment), and [website readiness](WEBSITE-READINESS.md) for release checks.

## Database configuration

The default path is:

```text
data/chaoshire.db
```

Override it using:

```text
CHAOSHIRE_DB_PATH=/path/to/chaoshire.db
```

SQLite write-ahead logging and foreign-key enforcement are enabled. Connections are committed or rolled back and always closed after use.

## Render free-tier limitation

Render's free service filesystem is ephemeral. History can survive an application process restart on the same instance but may disappear after a redeploy, instance replacement, or platform maintenance. No paid persistent disk is required for the portfolio demonstration, but this must not be described as durable cloud storage.

A production deployment should replace the SQLite repository with managed PostgreSQL or another approved database, with encryption, access control, backups, retention/deletion policies, regional data controls, and formal privacy review.

## API

```text
GET /api/audits?limit=50     # newest aggregate records
GET /api/audits/{audit_id}   # complete stored aggregate result
```

Unknown IDs return HTTP 404. The list limit is bounded to 1–100 records.

The in-memory upload slot is shared by the whole process, so on a public
deployment `/api/audit?dataset=uploaded`, `/api/audit/export`,
`/api/evidence?dataset=uploaded`, and the uploaded report endpoints return the
most recent upload made by *any* visitor. They expose the same aggregate
content described above and never the raw rows.
