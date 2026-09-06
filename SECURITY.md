# Security and data safety

ChaosHire's public deployment is a demonstration environment. **Do not upload real applicant or employee data.** Use synthetic or properly anonymized records only.

## Current limitations

- Uploaded CSV data and appeals are stored in process memory.
- There is no authentication or role-based access control in v0.1.
- The application has not undergone an independent security or privacy assessment.
- The demonstration is not designed for sensitive production workloads.

## Reporting a vulnerability

Please report security issues privately to the repository owner rather than opening a public issue containing exploitation details or sensitive information. Include affected component, reproduction steps, likely impact, and a suggested fix if available.

Production adoption would require authentication, authorization, encryption, secure storage, retention controls, audit logging, rate limiting, dependency scanning, privacy review, and legal review.
