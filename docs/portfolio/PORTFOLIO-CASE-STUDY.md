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
- 289 automated tests, 94.9% package coverage, and fairness policy enforcement in GitHub Actions. The figures are derived by `scripts/check_build_info.py` from a real test run, so the documents cannot outlive the code they describe.

## Measurable demonstration

The intentionally biased fixture scores **32/F** and **30/100** resilience. ChaosHire finds 169 gender-swap flips and 111 community-swap flips. The merit-based control scores **84/B** and **100/100** resilience; the CI policy passes LegacyCorp to MeritFirst and blocks the reverse release.

The third fixture is the argument in one line. **TalentFit v3** is a logistic
regression fitted to the same synthetic population with protected attributes
withheld. It is the **most accurate** of the three models (89.4% agreement with
the ground-truth label) and has **resilience 100/100**. It still fails the
four-fifths rule, with a **worst disparate impact of 0.727** (age band; gender
0.78), and scores **66/C**. The cause is the label, not the model. By sampling
chance the label's qualified rate differs between groups, and a perfect predictor
of it scores 68/C. The retained proxy features carry near-zero weight, and
retraining without them makes the result worse. The resilience score is labelled
*by construction*: a model with no protected inputs cannot flip on a swap.
Accuracy and counterfactual robustness are both necessary, and neither is a
fairness result. Its coefficients are pinned with a SHA-256 digest, and
`python -m chaoshire train --check` re-derives them in CI, so the result cannot
silently drift.

## Responsible boundaries

All built-in records and employers are synthetic. The platform supports investigation; it does not prove unlawful discrimination, provide legal advice, or make autonomous employment decisions. Raw uploaded rows are not persisted to audit history.

## Résumé bullets

- Built and deployed a FastAPI fairness-auditing platform for hiring models, combining disparate-impact, equal-opportunity, confidence intervals, intersectional analysis, and controlled counterfactual stress tests.
- Designed deterministic candidate-level evidence and SHA-256 experiment bundles, plus a CI/CD release gate that blocks fairness regressions with meaningful exit codes.
- Implemented configurable decision-CSV ingestion, privacy-conscious aggregate persistence, native PDF/offline HTML reports, security controls, and 289 tests at 94.9% coverage with a CI job that fails when any quoted figure stops matching a real test run.
- Removed per-group threshold "calibration" from the one-click mitigation set after identifying it as prohibited by 42 U.S.C. § 2000e-2(l), and reframed it as an acknowledgement-gated research contrast that cites the statute in every response.
