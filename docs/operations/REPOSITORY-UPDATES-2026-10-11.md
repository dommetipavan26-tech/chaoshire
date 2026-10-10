# Repository follow-up — 11 October 2026

This is a source-repository update to the 1 October audit, not a new production
readiness certification. Pull request #57 is open from the active branch. The
new hosted security jobs have passed on the PR revision; prior GitHub checks on
the base commit are not evidence for this follow-up.

## Opt-in private data mode

The public synthetic demo remains the default (`CHAOSHIRE_PRIVATE_MODE=0`). An
operator can set `CHAOSHIRE_PRIVATE_MODE=1` to require the existing
`CHAOSHIRE_API_KEY` for:

- the published audit list and individual audit records;
- the redacted appeal queue;
- reads of the shared uploaded-data slot, including audit/export, HTML/PDF
  reports, evidence bundles, and fairness review;
- upload, appeal, and connector writes, even if anonymous writes are otherwise
  configured as allowed.

With the mode enabled, missing key configuration fails closed with `503`, and a
missing or incorrect key on a configured deployment receives `401`. Public
posture details are withheld from `/api/meta`; the full posture remains on the
operator-authenticated `/api/ops/posture`. Synthetic reference/demo endpoints
remain public.

This is deliberately a **single shared operator boundary**. It is not user
accounts, tenant or per-audit ownership, delegated roles, a browser login, or
multi-tenant authorization. The public dashboard never receives the operator
key; use a trusted server-side API client for protected operations. The key does
not isolate two organizations that share it. Do not process real applicant data
on the public demo, and do not treat private mode as production readiness.

## Security and release-pipeline changes

`.github/workflows/security.yml` now configures:

- `pip-audit` and CodeQL (already present);
- actionlint validation for workflow syntax and expressions;
- Gitleaks with a full Git-history checkout (`fetch-depth: 0`), with PR comments
  and secret-bearing artifacts disabled;
- Trivy scanning of the built runtime image for OS and library vulnerabilities.
  Fixed HIGH/CRITICAL findings fail the job; unfixed findings are reported but
  do not block it.

The new jobs need their first hosted run on this update. Findings must be
reviewed and remediated; adding a scanner is not a clean-scan result.

The tagged release workflow now generates an SPDX JSON SBOM, includes it in the
release checksums/assets, and requests GitHub attestations for release
provenance and the SBOM. These steps run only on a release tag; no release or
attestation was created as part of this repository update. Verify released
files with `gh attestation verify <release-file> --repo
dommetipavan26-tech/chaoshire`.

## Verification status

The private-mode API tests cover authenticated and anonymous requests for the
history, appeal and uploaded-data read paths; they also confirm that the
synthetic demo remains available and that private posture is not disclosed.

<!-- LOCAL-VERIFICATION-START -->
- Default tests: **507 passed**, package coverage **97.10% measured** (2,475 / 2,549 statements; 74 missed); the configured minimum remains 90%.
- Build facts checked against the real run; trained-model digest matches exactly with **100% decision agreement**.
- Ruff lint/format, mypy (30 source files), `pip check`, `git diff --check`, and strict repository inventory: **152 files, 0 errors/warnings**.
- Wheel/sdist and isolated runtime-only installation smoke: PASS; version 0.24.0, 46 runtime files, six direct dependencies, and `postgres`/`maintenance` extras.
- Fairness release gate (legacy → fair): **PASS**, 84/B, resilience 100, worst disparate impact 0.8732.
- Local environment was Python 3.11.2. Docker, PostgreSQL and Playwright were not installed locally.
<!-- LOCAL-VERIFICATION-END -->

### Hosted verification (pull request #57)

At PR head `574dff3`, GitHub Actions passed the Python 3.11/3.12 quality jobs,
PostgreSQL 3.11/3.12, container smoke, browser/mobile, fairness, dependency
audit, CodeQL, actionlint, full-history Gitleaks, and Trivy container scan. The
first actionlint run exposed ShellCheck issues; those were fixed before this
passing run. Trivy is configured to ignore unfixed findings, so review its full
output for advisory context rather than treating the pass as zero findings.

Checks on the base revision remain historical context only. No deployment,
managed database provisioning, secret rotation, production scan triage, live-site
check, or release tag was performed.

## Still needs owner or independent execution

1. For real candidate data, decide the identity provider and true tenant/audit
   ownership model. Private mode is only a stopgap for one trusted operator.
2. Provision and validate an approved durable database, encryption, backups and
   restore, retention/deletion, regional data handling, incident response, and
   independent privacy/security/legal review. The repository does not create
   paid services or choose data-retention policy.
3. Complete manual rendered-contrast, keyboard, screen-reader and real-device
   accessibility reviews. Automated axe checks cannot resolve all gradient
   backgrounds.
4. Rerun the Adult benchmark from a verified source when download transport is
   available; the previous fresh-download attempt failed at the external
   transport layer. Do not present an old run as newly reproduced.
5. Review the full Trivy output for any unfixed findings and verify the first
   signed release attestations after a tagged release. The PR checks passed
   under their configured policies; neither is proof of a clean production
   environment.
