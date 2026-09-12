# ChaosHire portfolio evidence

## 20-second recruiter summary

ChaosHire is an open-source responsible-AI platform that stress-tests automated hiring decisions before they affect candidates. It combines statistical group audits, five controlled counterfactual experiments, candidate-level evidence, appeals, and a CI/CD fairness gate. Its deterministic public demo has 65 tests and 96.83% package coverage.

## Three-minute live-demo script

### 0:00–0:20 — Frame the problem

Open the landing page.

> “Normal dashboards ask whether groups received different outcomes. ChaosHire also asks whether the same candidate’s decision changes when only identity signals change.”

Point to the synthetic-data boundary and verified engineering proof.

### 0:20–0:50 — Establish the baseline

Select **Fairness Dashboard** and **LegacyCorp Screen v1**.

> “This intentionally biased fixture scores 42/F. The score is a risk signal for review—not legal certification.”

Mention that every run uses the same seed and 1,000 synthetic candidates.

### 0:50–1:25 — Break the decision safely

Open **Chaos Lab**. Run the gender-swap experiment.

> “Qualifications stay fixed. Only gender markers change. We get 169 decision flips, exposing identity sensitivity that an aggregate dashboard can miss.”

Show the deterministic experiment ID and before/after evidence.

### 1:25–1:55 — Show human impact

Open **Who Got Filtered Out**, then candidate **C-1046**.

> “This qualified candidate is rejected by the legacy fixture. ChaosHire connects the aggregate risk to a reviewable candidate story and an appeals path.”

### 1:55–2:25 — Demonstrate remediation

Open **Mitigations** and run the combined simulation.

> “Blind screening and proxy removal improve the synthetic fixture from 42/F to 83/B. This is a controlled simulation, not a claim that remediation is complete.”

### 2:25–2:50 — Enforce the standard

Open **Release Gate** and compare LegacyCorp with MeritFirst.

> “The same checks can block a weaker model in CI/CD, so fairness becomes an engineering release condition rather than a one-time report.”

### 2:50–3:00 — Close

> “ChaosHire’s contribution is the combination: measurement, counterfactual stress testing, human evidence, and release governance in one reproducible open-source workflow.”

## Résumé descriptions

### One line

Built **ChaosHire**, an open-source FastAPI responsible-AI platform that audits hiring decisions with statistical fairness metrics, five counterfactual Chaos experiments, candidate evidence, and CI/CD release gates; achieved **65 tests and 96.83% coverage**.

### Two bullets

- Engineered a deterministic hiring-AI audit platform with group/intersectional metrics, Wilson confidence intervals, counterfactual identity swaps, mitigation simulations, appeals, tamper-evident evidence, and automated model-release policy.
- Shipped a free public Render deployment with a responsive dependency-free UI, OpenAPI documentation, scikit-learn adapter example, browser/mobile automation, **65 tests**, and **96.83% package coverage**.

## Evidence checklist

- Public app: <https://chaoshire.onrender.com>
- API docs: <https://chaoshire.onrender.com/docs>
- Source: <https://github.com/dommetipavan26-tech/chaoshire>
- Latest release: <https://github.com/dommetipavan26-tech/chaoshire/releases/latest>
- Desktop landing screenshot: `docs/assets/landing-desktop.png`
- Mobile landing screenshot: `docs/assets/landing-mobile.png`
- Dashboard screenshot: `docs/assets/dashboard-desktop.png`
- scikit-learn integration: `docs/SCIKIT-LEARN-INTEGRATION.md`

All screenshots and claims must be refreshed after production deployment. Do not present synthetic outcomes as findings about a real employer.