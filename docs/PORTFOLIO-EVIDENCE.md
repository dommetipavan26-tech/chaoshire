# Portfolio evidence pack — ChaosHire v0.21.0

Everything on this page is derived from the running application, not from memory. The numbers
are re-checked by `python scripts/verify_quality_claims.py` in the `Quality checks` job, so a
stale claim fails CI instead of shipping.

## 20-second recruiter summary

> ChaosHire is an open-source responsible-AI platform that stress-tests automated hiring
> decisions before they affect candidates. It combines statistical group audits, five
> controlled counterfactual experiments, candidate-level evidence, appeals, and a CI/CD
> fairness release gate. The public demo is deterministic: 82 core tests, 96.83% package
> coverage, and a deployed v0.21.0 release.

## Three-minute live-demo script

**0:00–0:20 — Frame the problem.** Open the landing page.
“Ordinary dashboards ask whether groups got different outcomes. ChaosHire also asks whether the
*same* candidate’s decision changes when only identity signals change.” Point at the
synthetic-data boundary and the verified-statistics strip.

**0:20–0:50 — Establish the baseline.** Choose *Fairness Dashboard* with **LegacyCorp Screen v1**.
“This deliberately biased fixture scores 42/F. The Fairness Risk Score is a review priority — it
is not a legal certification.” Every run uses the same seed and 1,000 synthetic candidates.

**0:50–1:25 — Break the decision safely.** Open **⚡ Chaos Lab** and run the suite.
“Qualifications stay fixed; only gender markers move, and 169 decisions flip (16.9%). Community
swapping flips 111, and the ageing stress test newly rejects 32.7% of 388 hires.” Show the
deterministic experiment ID `EXP-24D2842B44C7` and the before/after evidence table.

**1:25–1:55 — Show human impact.** Open **Who Got Filtered Out** (441 rejected, 42 of them truly
qualified), then look up **C-1046** in **Appeals**. “Zara Lopez is rejected at 0.4647 by the legacy
fixture. ChaosHire connects the aggregate risk to a reviewable candidate story and an appeals path.”
File an appeal to show automatic triage.

**1:55–2:25 — Demonstrate remediation.** Open **Mitigations**, tick all three, re-audit.
“Blind screening, proxy removal and threshold calibration move the synthetic fixture from 42/F to
83/B — a controlled simulation, not a claim that remediation is finished.”

**2:25–2:50 — Enforce the standard.** Open **Release Gate**; run with the default floors, then raise
the risk-score floor to 99. “The same checks block a weaker model in CI/CD, so fairness becomes a
release condition instead of a one-time report.” Compare LegacyCorp (42/F, resilience 30) with
MeritFirst (86/B, resilience 100).

**2:50–3:00 — Close.** “The contribution is the combination: measurement, counterfactual stress
testing, human evidence and release governance in one reproducible open-source workflow — plus an
adapter so a real scikit-learn model can be audited exactly the same way.”

## Résumé descriptions

**One line**

> Built ChaosHire, an open-source FastAPI responsible-AI platform that audits hiring decisions with
> statistical fairness metrics, five counterfactual chaos experiments, candidate-level evidence and
> CI/CD release gates; 82 tests at 96.83% coverage, deployed on Render.

**Two bullets**

> - Engineered a deterministic hiring-AI audit platform with group and intersectional metrics, Wilson
>   confidence intervals, counterfactual identity swaps, mitigation simulations, appeals,
>   tamper-evident SHA-256 evidence bundles, and automated model-release policies.
> - Shipped a free public Render deployment with a dependency-free responsive UI, OpenAPI docs, a
>   scikit-learn decision-adapter example, Playwright desktop/mobile automation, 82 tests and 96.83%
>   package coverage, with published quality claims verified in CI.

**Interview follow-ups this project can answer**

| Question | Where the answer lives |
|---|---|
| Why a risk score and not “certification”? | `docs/METHODOLOGY.md`, landing boundary note |
| How do you avoid over-claiming on statistics? | Exploratory p-values, Wilson intervals, minimum-cell rules |
| How would a real model integrate? | `examples/scikit_learn_adapter.py`, `docs/SCIKIT-LEARN-INTEGRATION.md` |
| How is state handled on a free tier? | `docs/PERSISTENCE.md`, `docs/MONITORING.md` |
| What breaks in production? | `docs/MONITORING.md` runbook + `/api/ready` + cold-start copy in the UI |

## Verified demonstration facts

| Claim | Value | How to reproduce |
|---|---|---|
| Core tests | 82 | `python -m pytest -q` |
| Package coverage | 96.83% (floor 90%) | `python -m pytest --cov=chaoshire -q` |
| Chaos experiments | 5 | `python -m pytest tests/test_workflows.py -q` |
| LegacyCorp risk score | 42 / F | `GET /api/audit?model=legacy` |
| MeritFirst risk score | 86 / B | `GET /api/audit?model=fair` |
| Gender-swap flips | 169 (16.9%) | `GET /api/chaos?model=legacy` |
| Community-swap flips | 111 (11.1%) | `GET /api/chaos?model=legacy` |
| Ageing stress rejections | 32.7% of 388 | `GET /api/chaos?model=legacy` |
| Qualified candidates rejected | 42 of 441 | `GET /api/filtered?model=legacy` |
| Mitigated fixture | 42 / F → 83 / B | `POST /api/mitigate` with all three strategies |
| Experiment ID | `EXP-24D2842B44C7` | deterministic, SHA-256 derived |
| scikit-learn example | naive blocked, blind released | `python -m examples.scikit_learn_adapter` |

## Screenshot and recording checklist

| Asset | Path | Command |
|---|---|---|
| Landing (desktop 1440) | `docs/assets/landing-desktop.png` | `python scripts/capture_portfolio.py` |
| Landing (mobile 390) | `docs/assets/landing-mobile.png` | `python scripts/capture_portfolio.py` |
| Fairness dashboard | `docs/assets/dashboard-desktop.png` | `python scripts/capture_portfolio.py` |
| Chaos Lab | `docs/assets/chaos-lab-desktop.png` | `python scripts/capture_portfolio.py` |
| Release gate | `docs/assets/release-gate-desktop.png` | `python scripts/capture_portfolio.py` |
| Architecture | `docs/ARCHITECTURE.svg` | committed source of truth |

For the recording, use the script above at 1× speed, keep the address bar visible for the first
five seconds (it shows the public deployment), and never narrate a synthetic result as a finding
about a real employer.

## Public evidence links

- Application: <https://chaoshire.onrender.com>
- OpenAPI docs: <https://chaoshire.onrender.com/docs>
- Source: <https://github.com/dommetipavan26-tech/chaoshire>
- Latest release: <https://github.com/dommetipavan26-tech/chaoshire/releases/latest>
- CI (quality, browser, fairness gate, security): <https://github.com/dommetipavan26-tech/chaoshire/actions>

> Re-capture screenshots and re-run the claims script after every production deployment. Screenshots
> are evidence of the build they came from, not of “the current app”.
