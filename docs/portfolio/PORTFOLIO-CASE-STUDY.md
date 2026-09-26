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
- API-key write protection with a generated deployment secret, separate read and write rate limits, bounded appeal queue, nonce-based Content-Security-Policy, request IDs, readiness checks, operational metrics, CodeQL, dependency audit, Dependabot, and automated releases.
- 294 automated tests, 95.0% package coverage, and fairness policy enforcement in GitHub Actions. The figures are derived by `scripts/check_build_info.py` from a real test run, so the documents cannot outlive the code they describe.

## Measurable demonstration

The intentionally biased fixture scores **32/F** and **30/100** resilience. ChaosHire finds 169 gender-swap flips and 111 community-swap flips. The merit-based control scores **84/B** and **100/100** resilience; the CI policy passes LegacyCorp to MeritFirst and blocks the reverse release.

The third fixture is the one we trained, and its first version failed. The
original **TalentFit v3**, a logistic regression fitted to the ground-truth label
with protected attributes withheld, was the **most accurate** model (89.4%) and
still scored **66/C**. It failed the four-fifths rule (worst disparate impact
0.727) because the label itself is uneven across groups by sampling chance; a
perfect predictor of it scores 68/C. The **upgrade** drops the proxy features and
replaces the error-rate cutoff with one cost-sensitive cutoff for everyone, which
treats a wrongly rejected qualified candidate as twice as costly as a wrongly
advanced one. It now scores **80/B**, passes the four-fifths rule (0.814), and
wrongly rejects **21** qualified candidates against MeritFirst's 34. On 49
synthetic populations it never saw it averages **74.1** against MeritFirst's
72.1. The trade-off is stated as well: it is slightly less accurate than
MeritFirst out of sample, and it still trails it by 4 points on the audited
fixture because the cutoff was fixed as policy, not tuned to win. Its
coefficients and decision policy are pinned with a SHA-256 digest, and
`python -m chaoshire train --check` re-derives them in CI.

## Responsible boundaries

All built-in records and employers are synthetic. The platform supports investigation; it does not prove unlawful discrimination, provide legal advice, or make autonomous employment decisions. Raw uploaded rows are not persisted to audit history.

## Résumé bullets

- Built and deployed a FastAPI fairness-auditing platform for hiring models, combining disparate-impact, equal-opportunity, confidence intervals, intersectional analysis, and controlled counterfactual stress tests.
- Designed deterministic candidate-level evidence and SHA-256 experiment bundles, plus a CI/CD release gate that blocks fairness regressions with meaningful exit codes.
- Implemented configurable decision-CSV ingestion, privacy-conscious aggregate persistence, native PDF/offline HTML reports, security controls, and 294 tests at 95.0% coverage with a CI job that fails when any quoted figure stops matching a real test run.
- Removed per-group threshold "calibration" from the one-click mitigation set after identifying it as prohibited by 42 U.S.C. § 2000e-2(l), and reframed it as an acknowledgement-gated research contrast that cites the statute in every response.
