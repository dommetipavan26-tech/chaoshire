# Repository verification and update plan — 27 October 2026

## Executive summary

ChaosHire's application code and package build are healthy. After the dependency remediation in this branch, local Python 3.11 verification passes all **507 default tests at 97.10% package coverage**, as well as lint, formatting, typing, model reproducibility, the fairness gate, and an isolated installed-wheel smoke test.

The initial audit found advisories in the dependency resolutions and an `httpx2`/`httpcore2` version mismatch. Both were corrected locally, and the regenerated Python 3.11/3.12 locks now pass `pip-audit`. The remediation passed hosted CI on [PR #86](https://github.com/dommetipavan26-tech/chaoshire/pull/86), including Python 3.11/3.12, PostgreSQL, browser, dependency audit, Trivy, CodeQL, and container smoke; PR #86 was subsequently merged to `main` on 28 October 2026 (commit `ea69419`). This is a 27 October snapshot and predates the separate TalentFit v4 model update documented in [the 28 October model report](MODEL-UPGRADE-2026-10-28.md). No deployment or package release is certified here. This report does not authorize real applicant data.

## Remediation follow-up (27 October 2026)

The initial findings below were acted on in the current Arena branch:

- Regenerated both constraint files with `scripts/compile_constraints.py` after widening the maintenance `uv` range. The refreshed resolutions now contain `brotli==1.2.1`, `certifi==2026.10.23`, `filelock==4.2.4`, `setuptools==84.2.1`, and `uv==0.13.6`; both also pin the compatible `httpx2==2.16.0` / `httpcore2==2.16.0` pair.
- `pip-audit` now reports **no known vulnerabilities** for either Python constraint file.
- Re-ran the default suite on the refreshed Python 3.11 set: **507 passed, 97.10% coverage**. Ruff, mypy, strict repository checks, model reproducibility, fairness gate, wheel/sdist build, isolated distribution smoke, and installation of browser/examples/PostgreSQL/maintenance extras also pass.
- Applied the setup-python and CodeQL action commit updates represented by Dependabot PRs #84 and #85. Added a weekly Docker ecosystem to Dependabot to track the Dockerfile base image.
- The report's inventory/index are refreshed. No application scoring, API, or model behavior was changed.

**Hosted validation — PR #86:** all 13 reported checks passed, including [quality, PostgreSQL, and container smoke](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/40578244144), [browser/Chromium](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/40578244050), [dependency audit, Trivy, CodeQL, Gitleaks, and workflow lint](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/40578244045), and the [fairness gate](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/40578244085). PR #86 was merged to `main` on 28 October 2026; the hosted runs above were green before merge. The live-site workflow is push-to-main/manual and was not run for that proposed revision. Docker and PostgreSQL remain unavailable locally. I attempted to enable Dependabot alerts through the GitHub API, but the connected integration returned HTTP 403 (`Resource not accessible by integration`); a repository admin must turn on alerts/security updates in GitHub settings. No deployment or release tag was created.

## Snapshot and scope

| Item | Finding |
|---|---|
| Repository / branch | `dommetipavan26-tech/chaoshire` / `arena/b3702a97-chaoshire` |
| Base revision checked | `6c2fe670ad65d3a160961a9e1a4707f399212ccf` (`6c2fe67`), same revision as `main` at initial inspection; remediation is now in the working tree |
| Package version | `0.24.0` |
| Local runtime | Python 3.11.2 on Linux; Node.js 22.22.3 |
| Initial worktree | Clean; no application-code changes were made during verification |
| Local limitations | No local Python 3.12, Docker engine, Chromium browser binary, or PostgreSQL service; Playwright is installed, but those checks still need hosted CI |
| Current release | Latest GitHub Release is `v0.23.3`; `v0.24.0` has not been published |

This working tree contains the report/index/inventory plus the dependency-lock refresh, maintenance-tool range update, immutable GitHub Action SHA bumps, Docker Dependabot schedule, and checker wording update. Application runtime logic was left unchanged. Test/build outputs and the temporary virtual environment are ignored local artifacts.

## Local verification

Commands were run against the checked-out source using the pinned Python 3.11 resolution where applicable.

| Check | Result |
|---|---|
| Default pytest suite | **507 passed** in 61 seconds after the dependency refresh |
| Coverage | **97.10%** (2,475 / 2,549 statements); configured floor is 90% |
| Ruff lint and format | Pass; Ruff 0.17.3 reports 107 files already formatted |
| Mypy | Pass; no issues in 30 configured source files |
| Strict repository inventory | Pass; 153 files, 0 errors, 0 warnings after the report and automation updates |
| Build-fact drift check | Pass; confirms 507 tests and 97.1% |
| `pip check` / `git diff --check` | Pass |
| Trained-model reproducibility | Pass; pinned digest matches and decision agreement is **100%** |
| Holdout comparison | Pass across 49 populations; trained model mean total 76.04, fair fixture 74.39 |
| Fairness release gate | **PASS**; fair fixture 84/B, resilience 100, worst disparate impact 0.8732 |
| Wheel and source distribution | Build passes; installed-wheel checker passes in an isolated runtime-only environment |
| Distribution contents | Version 0.24.0, 46 runtime files, six direct runtime dependencies, `postgres` and `maintenance` extras |
| Adapter example | Pass using the documented module invocation: `python -m examples.sklearn_decision_adapter` |

The first manual example invocation used direct-file execution and could not import the repository package; the documented/CI module invocation passed. This was an invocation-path issue, not a failing example.

## Hosted verification before remediation

For base revision `6c2fe67`, the 20 October GitHub runs passed quality on Python 3.11/3.12, PostgreSQL integration on both versions, container smoke, browser checks, the fairness gate, the security suite, and live-site verification including the cold-start job:

- [Quality checks](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/39382685750)
- [Browser checks](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/39382685525)
- [Fairness gate](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/39382685399)
- [Security checks, 20 October](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/39382685476)
- [Live-site and cold-start checks](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/39382685396)

The [26 October scheduled security run](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/40296194712) on the base revision failed `dependency-audit` and `container-scan`. At initial inspection, [Dependabot PRs #79–#85](https://github.com/dommetipavan26-tech/chaoshire/pulls) were all reported `BLOCKED`; PR #81 had additional dependency-install failures. Their branch statuses do not reflect the remediation now in this working tree. Dependabot's security-alert API reports that **Dependabot alerts are disabled** for this repository, even though weekly version-update PRs are configured; the attempt to enable alerts with the connected GitHub integration was denied with HTTP 403.

### Python dependency findings before remediation

The initial `pip-audit` run against both committed Linux/Python constraint files found the same **nine advisory records across five pinned packages**. These resolutions cover runtime plus developer, browser, build, and maintenance tooling; a finding in the full toolchain is not automatically a claim that the affected package is shipped in the production runtime image.

| Package pinned before remediation | Advisory IDs reported | First fixed version reported | Related open PR |
|---|---|---|---|
| `brotli==1.2.0` | `PYSEC-2026-4322`, `GHSA-9v8h-qqgm-4m35` | `1.2.1` | None |
| `certifi==2026.7.22` | `PYSEC-2026-4320` | `2026.10.18` / `2026.10.19` | [#80 proposes 2026.10.23](https://github.com/dommetipavan26-tech/chaoshire/pull/80) |
| `filelock==4.0.12` | `CVE-2026-112940`, `CVE-2026-112913`, `CVE-2026-112907` | `4.2.1` | None |
| `setuptools==84.0.0` | `GHSA-xmj3-9gf7-h52w` | `84.1.0` | None |
| `uv==0.12.22` | `PYSEC-2026-4321` | `0.13.4` | [#82 proposes 0.13.5](https://github.com/dommetipavan26-tech/chaoshire/pull/82) |

These findings were reproduced for both `constraints/requirements-py311.txt` and `constraints/requirements-py312.txt`. The regenerated files now use Brotli 1.2.1, certifi 2026.10.23, filelock 4.2.4, setuptools 84.2.1, and uv 0.13.6. A new audit of each full resolution reports **no known vulnerabilities**.

The 26 October Trivy failure was on the pre-remediation base revision; its detailed finding list was not available through the sandbox's GitHub log-download route, and Docker is not installed locally. The updated image scan passes on PR #86 under the workflow's fixed CRITICAL/HIGH policy (`ignore-unfixed: true`); this is not a claim of zero unfixed findings. No suppression or speculative base-image change was made.

## Remaining actions, in priority order

### P0 — dependency audit (resolved locally and in hosted checks)

- Both constraint files were regenerated. The five advisory packages are fixed at Brotli 1.2.1, certifi 2026.10.23, filelock 4.2.4, setuptools 84.2.1, and uv 0.13.6. Both `pip-audit` runs now report no known vulnerabilities.
- The `uv` maintenance range is now `>=0.13.5,<0.14`. `httpx2` and `httpcore2` are both 2.16.0, resolving the exact-pin conflict that blocked PR #81.
- The full 507-test Python 3.11 suite, lint, typing, trained-model check, fairness gate, build, isolated distribution smoke, and all-manifest installs pass locally. PR #86 also passed hosted Python 3.11/3.12, PostgreSQL, browser, Trivy, and container-smoke checks.
- GitHub Dependabot security alerts could not be enabled with the connected integration (HTTP 403). A repository admin must enable alerts/security updates in GitHub settings; version-update scheduling alone does not do this.

### P1 — hosted security and release

- PR #86's Trivy scan passes. Its policy ignores unfixed findings, so an owner may review the 26 October base-run details if they want full advisory context; no suppression or unverified base-image change is needed for the current gate.
- The `python:3.12-slim` tag is mutable. A weekly Docker update entry has now been added to Dependabot; consider pinning a reviewed image digest after verifying the image and Trivy result.
- The constraint refresh incorporates the updates from Dependabot PRs #79–#83; the compatible HTTPX2/Core2 pair is included. The workflow commits represented by PRs #84–#85 are also updated in this branch. Those original PRs' existing check statuses remain historical until their heads or this branch are rerun.

### P1 — prepare the `0.24.0` release

Security and quality gates passed on merged PR #86. The separate package-release decision still requires owner review of the current model and production-readiness work before publishing the already-declared version `0.24.0`; the latest GitHub Release recorded at this checkpoint was `v0.23.3`. Follow the [release checklist](RELEASE-CHECKLIST.md), then verify the first `0.24.0` SBOM/provenance attestations. No `0.24.0` release or attestation has been created by this remediation. Reconcile the historical pending-tag entries in [`docs/planning/TODO.md`](../planning/TODO.md) rather than blindly creating obsolete tags.

### P2 — owner / product decisions before real applicant data

The repository documents an opt-in **single-operator** private mode, not user accounts, tenant isolation, or per-audit ownership. Before handling real applicant data, design and independently review identity and access boundaries, approved durable storage, encryption, retention/deletion, backup/restore, incident response, and legal/privacy controls. Do not use the public demo for sensitive data.

Manual gradient-contrast, screen-reader, and physical-device checks are also still needed; automated browser/axe results do not settle those issues. The fresh UCI Adult benchmark rerun remains a research follow-up, not a release blocker for the synthetic demo.

## Verification commands

From the repository root, to repeat the current verification:

```bash
python scripts/compile_constraints.py
python -m pip_audit -r constraints/requirements-py311.txt --no-deps --disable-pip
python -m pip_audit -r constraints/requirements-py312.txt --no-deps --disable-pip
python -m ruff check .
python -m ruff format --check .
python -m mypy --python-version 3.11
python -m pytest --cov=chaoshire --cov-report=term-missing --cov-report=json -q
python scripts/check_build_info.py --coverage-json coverage.json
python -m chaoshire train --check
python -m chaoshire gate --baseline legacy --candidate fair
python -m build
python scripts/check_distribution.py --wheel dist/chaoshire-*.whl --sdist dist/chaoshire-*.tar.gz --constraints constraints/requirements-py311.txt
```

Use CI's Python 3.12 job for the 3.12 runtime check; a 3.11 machine cannot prove 3.12 execution. Keep the current branch name fixed and do not publish or tag a release until the owner approves the release and production-readiness decisions.
