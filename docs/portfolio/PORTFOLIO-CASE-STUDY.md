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
- API-key write protection plus opt-in single-operator private reads for shared history, appeal listings, and uploaded data (not tenant isolation), separate read/write limits, bounded appeals, nonce-based CSP, request IDs, readiness checks, and operational metrics. CI includes CodeQL and dependency auditing; actionlint, full-history Gitleaks, and Trivy OS/library scanning passed on PR #57 under their configured policies. Results are revision-specific, and scanner findings still require review. Dependabot and automated releases remain in place.
- 513 automated tests, 96.6% package coverage, and fairness policy enforcement in GitHub Actions. The figures are derived by `scripts/check_build_info.py` from a real test run, so the documents cannot outlive the code they describe.

## Measurable demonstration

The intentionally biased fixture scores **32/F** and **30/100** resilience. ChaosHire finds 169 gender-swap flips and 111 community-swap flips. The merit-based control scores **84/B** and **100/100** resilience; the CI policy passes LegacyCorp to MeritFirst and blocks the reverse release.

The third fixture is the one we trained, and its first version failed. The
original **TalentFit v3**, a logistic regression fitted to the synthetic label
with protected attributes withheld, was the **most accurate** model (89.4%) and
still scored **66/C**. It failed the four-fifths rule (worst disparate impact
0.727); even a perfect predictor of the label scores 68/C. The subsequent
proxy-free v3 earned **80/B** at a global 2:1 cost-sensitive cutoff. The latest
**TalentFit v4** keeps protected and proxy features out and changes only that
single global operating point to P(qualified) ≥ 1/4 (a synthetic 3:1
false-rejection cost). A fixed policy study selected it from five candidate
cost ratios on 49 synthetic tuning populations, subject to a mean-accuracy
floor of 80%, then checked it on 50 disjoint populations.

On the demo fixture, v4 scores **85/B**, with worst disparate impact **0.874**
(gender), 83.1% accuracy, and **11** qualified rejections (down from 21 for v3
and 34 for MeritFirst). On the separate holdout it averages **78.40** vs v3's
74.62, worst-DI pass rate 74% vs 68%, and 9.02 vs 19.84 missed qualified
candidates. The trade-off is explicit: mean accuracy falls from 85.05% to
80.99%, and false-positive rate rises from 21.61% to 30.18%. Part of the score
gain is mechanical because advancing more candidates narrows selection-rate
gaps. All records are synthetic; these results are not evidence of fair
outcomes for actual applicants or employers. The coefficient digest and policy
metadata are pinned, `train --check` verifies reproducibility, and
`train --policy-study` reproduces the selection and holdout evaluation.

## Responsible boundaries

All built-in records and employers are synthetic. The platform supports investigation; it does not prove unlawful discrimination, provide legal advice, or make autonomous employment decisions. Raw uploaded rows are not persisted to audit history.

## Résumé bullets

- Built and deployed a FastAPI fairness-auditing platform for hiring models, combining disparate-impact, equal-opportunity, confidence intervals, intersectional analysis, and controlled counterfactual stress tests.
- Designed deterministic candidate-level evidence and SHA-256 experiment bundles, plus a CI/CD release gate that blocks fairness regressions with meaningful exit codes.
- Implemented configurable decision-CSV ingestion, privacy-conscious aggregate persistence, native PDF/offline HTML reports, security controls, and 513 tests at 96.6% coverage with a CI job that fails when any quoted figure stops matching a real test run.
- Removed per-group threshold "calibration" from the one-click mitigation set after identifying it as prohibited by 42 U.S.C. § 2000e-2(l), and reframed it as an acknowledgement-gated research contrast that cites the statute in every response.
