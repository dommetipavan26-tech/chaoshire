# ChaosHire — portfolio case study

## One-line summary

Built an open-source fairness-auditing platform that stress-tests hiring-model decisions with controlled counterfactual experiments, produces candidate-level evidence, and blocks regressions in CI/CD.

## Problem

Group dashboards reveal unequal outcomes but often cannot show whether an individual decision depends on identity. Hiring teams also lack a repeatable way to compare model versions, preserve evidence, and stop fairness regressions before release.

## Solution

ChaosHire combines group metrics, uncertainty estimates, pairwise intersectional analysis, five controlled Chaos experiments, explanations, appeals, mitigation simulations, model comparison, an automated release gate, and a deterministic review agent. Companies can upload decision outcomes without sharing model weights.

## Engineering highlights

- FastAPI service and dependency-free responsive dashboard deployed in Docker on Render.
- Deterministic 1,000-candidate fixture with reproducible experiment and review IDs.
- Configurable CSV schema, Wilson confidence intervals, two-proportion indicators, and intersectional analysis.
- SHA-256 tamper-evident evidence, offline HTML and native PDF reports.
- Optional API-key write protection, rate limiting, request IDs, readiness checks, operational metrics, CodeQL, dependency audit, Dependabot, and automated releases.
- 65 automated tests, more than 96% package coverage, and fairness policy enforcement in GitHub Actions.

## Measurable demonstration

The intentionally biased fixture scores 42/F and 30/100 resilience. ChaosHire finds 169 gender-swap flips and 111 community-swap flips. The cleaner fixture scores 86/B and 100/100 resilience; the CI policy passes LegacyCorp to MeritFirst and blocks the reverse release.

## Responsible boundaries

All built-in records and employers are synthetic. The platform supports investigation; it does not prove unlawful discrimination, provide legal advice, or make autonomous employment decisions. Raw uploaded rows are not persisted to audit history.

## Résumé bullets

- Built and deployed a FastAPI fairness-auditing platform for hiring models, combining disparate-impact, equal-opportunity, confidence intervals, intersectional analysis, and controlled counterfactual stress tests.
- Designed deterministic candidate-level evidence and SHA-256 experiment bundles, plus a CI/CD release gate that blocks fairness regressions with meaningful exit codes.
- Implemented configurable decision-CSV ingestion, privacy-conscious aggregate persistence, native PDF/offline HTML reports, security controls, and 65 tests at over 96% coverage.
