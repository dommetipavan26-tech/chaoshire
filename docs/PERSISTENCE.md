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
- Certificate score and grade

## Not persisted

ChaosHire deliberately does not write the following upload contents to SQLite:

- Candidate IDs
- Candidate names
- Individual decisions
- Individual qualification labels
- Complete uploaded rows
- Original CSV text

The raw parsed DataFrame remains in process memory only so the current session can render and export its aggregate audit. A restart clears those rows.

The public demonstration has no authentication. Audit names, aggregate metrics, and configurations returned by the history API are visible to every visitor. Use synthetic data and non-sensitive audit names only.

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
