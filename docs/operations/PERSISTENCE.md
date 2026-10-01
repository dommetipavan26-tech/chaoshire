# Audit-history persistence and privacy

ChaosHire stores **operator-published aggregate audit evidence** in SQLite by default. Anonymous uploads are computed and returned without publication or persistence. This document defines those different lifecycles.

## Anonymous uploads

A successful anonymous CSV upload returns `published: false`, `audit_id: null`, its aggregate audit, interpretation settings, and warnings. It does **not** create a history record or replace the process-wide uploaded-data slot. The server discards the parsed rows after completing the request.

The dashboard keeps the aggregate result in page memory and its **Download JSON audit** button saves that exact result locally. Reloading the page clears this client-local result. The shared `/api/audit/export`, HTML/PDF report, and evidence endpoints are not exports of an anonymous visitor's upload.

## Persisted operator publications

Only an upload authenticated with the operator API key is published. For each such audit, ChaosHire saves:

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

These aggregates can still be sensitive, especially for small groups or identifying audit names. Publication is a separate action from computing an audit; it is not private storage.

## Not persisted

ChaosHire deliberately does not write the following upload contents to the history database:

- Candidate IDs
- Candidate names
- Individual decisions
- Individual qualification labels
- Complete uploaded rows
- Original CSV text

For an **operator-published** upload, the raw parsed DataFrame is retained only in the shared process-local slot alongside its aggregate result. A later publication replaces it and a restart clears it. This is not a per-visitor session. For anonymous uploads, those rows are discarded after the response.

The public demonstration has no visitor accounts or per-audit read authorization. Published audit names, aggregate metrics, and configurations returned by the history API are visible to every visitor. Use synthetic data and non-sensitive audit names only.

## Site preferences and anonymous analytics

The browser uses `localStorage` to remember an explicit analytics Allow or Reject choice. No tracking cookies or third-party analytics scripts are loaded. Only after Allow does the browser send an allowlisted page-section name to `POST /api/analytics/view`; it sends no visitor ID, name, candidate ID, or referrer. Daily aggregate counters are held in process memory for at most 30 UTC days, reset on restart, and can be read only through operator-authenticated `GET /api/ops/analytics`. Separate short-term rate-limit buckets keep client IP identifiers in a bounded process-local map (at most 4,096 keys). Expired windows are lazily removed on new limiter activity or operator snapshots, without requiring a restart; those identifiers are not copied into analytics counters. Hosting-provider access logs may have their own retention.

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

SQLite write-ahead logging and foreign-key enforcement are enabled. Connections are committed or rolled back and always closed after use. The optional PostgreSQL adapter is selected with `CHAOSHIRE_DB_BACKEND=postgres` and `CHAOSHIRE_DATABASE_URL`; it additionally requires the `psycopg2` driver (`python -m pip install ".[postgres]"` or `-r requirements-postgres.txt`). See [platform engineering](../portfolio/PORTFOLIO-PLATFORM.md). Nine isolated service-backed tests verified PostgreSQL 16.2 locally; a configured production URL still does not prove the owner's database is healthy.

## Render free-tier limitation

Render's free service filesystem is ephemeral. History can survive an application process restart on the same instance but may disappear after a redeploy, instance replacement, or platform maintenance. No paid persistent disk is required for the portfolio demonstration, but this must not be described as durable cloud storage.

A production deployment needs an approved durable database, encryption, access control, backups, retention/deletion policies, regional data controls, and formal privacy review. The existing PostgreSQL adapter alone does not supply those controls.

## API and shared latest-publication slot

```text
GET /api/audits?limit=50     # newest published aggregate records
GET /api/audits/{audit_id}   # complete stored aggregate result
```

Unknown IDs return HTTP 404. The list limit is bounded to 1–100 records.

The in-memory uploaded-data slot is shared by the whole process, so `/api/audit?dataset=uploaded`, `/api/audit/export`, `/api/evidence?dataset=uploaded`, and the uploaded report endpoints return the **most recent operator-published upload**, not a caller-specific result. They expose aggregates, never raw rows. Before any publication these uploaded-data endpoints return 404; an anonymous upload does not change that. Persisted history records may outlive the latest-upload slot after a process restart.
