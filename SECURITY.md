# Security and data safety

ChaosHire's public deployment is a demonstration environment. **Do not upload real applicant or employee data.** Use synthetic or properly anonymized records only.

## Current limitations

- Raw uploaded CSV rows and appeals are stored in process memory.
- Named aggregate audit results and interpretation settings are stored in SQLite; raw candidate rows and IDs are not written to history.
- Render free-tier storage is ephemeral and must not be treated as a durable record system.
- Optional `CHAOSHIRE_API_KEY` protection is available for uploads and appeal submissions, but the public portfolio demo may intentionally run without it; full user accounts and role-based authorization are not implemented.
- Aggregate history remains readable to visitors when the portfolio demo is operated publicly.
- Responses include request IDs, security headers, a same-origin content policy, request-size enforcement, and optional rate limiting; these controls have not undergone an independent security assessment.
- The application has not undergone an independent security or privacy assessment.
- The demonstration is not designed for sensitive production workloads.

## Reporting a vulnerability

Please report security issues privately to the repository owner rather than opening a public issue containing exploitation details or sensitive information. Include affected component, reproduction steps, likely impact, and a suggested fix if available.

Production adoption would require authentication, authorization, encryption, secure storage, retention controls, audit logging, rate limiting, dependency scanning, privacy review, and legal review.
