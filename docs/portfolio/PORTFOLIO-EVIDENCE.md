# ChaosHire portfolio evidence

## 20-second recruiter summary

ChaosHire is an open-source responsible-AI platform that stress-tests automated hiring decisions before they affect candidates. It combines statistical group audits, five controlled counterfactual experiments, candidate-level evidence, appeals, and a CI/CD fairness gate. The current repository baseline has 513 tests and 96.6% package coverage, measured from a real local run and guarded by a CI job that fails on drift. The hand-managed public Render deployment may lag until the owner deploys this revision.

## Three-minute live-demo script

### 0:00–0:20 — Frame the problem

Open the landing page.

> “Normal dashboards ask whether groups received different outcomes. ChaosHire also asks whether the same candidate’s decision changes when only identity signals change.”

Point to the synthetic-data boundary and verified engineering proof.

### 0:20–0:50 — Establish the baseline

Select **Fairness Dashboard** and **LegacyCorp Screen v1**.

> “This intentionally biased fixture scores 32/F — 27.1 of 85 available points measured. The score is a risk signal for review—not legal certification.”

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

> “Blind screening and proxy removal in this separate mitigation simulation move the synthetic fixture from 32/F to 80/B. The trained TalentFit v4 reference is a different result: 85/B under one global cutoff, with lower accuracy and more false positives than v3. Neither is a claim that remediation is complete or that a real system is fair. Per-group threshold calibration is not offered: 42 U.S.C. § 2000e-2(l) bars different cutoff scores by race, colour, religion, sex or national origin.”

### 2:25–2:50 — Enforce the standard

Open **Release Gate** and compare LegacyCorp with TalentFit v4.

> “The gate checks risk score, resilience, disparate impact, and an 80% accuracy floor against the bundled synthetic label. TalentFit v4 passes this fixture; raising the floor to 84% blocks it. This is a demo guardrail—not a real-world performance estimate.”

### 2:50–3:00 — Close

> “ChaosHire’s contribution is the combination: measurement, counterfactual stress testing, human evidence, and release governance in one reproducible open-source workflow.”

## Résumé descriptions

### One line

Built **ChaosHire**, an open-source FastAPI responsible-AI platform that audits hiring decisions with statistical fairness metrics, five counterfactual Chaos experiments, candidate evidence, and CI/CD release gates; achieved **513 tests and 96.6% coverage**.

### Two bullets

- Engineered a deterministic hiring-AI audit platform with group/intersectional metrics, Wilson confidence intervals, counterfactual identity swaps, mitigation simulations, appeals, tamper-evident evidence, and automated model-release policy.
- Shipped a free public Render deployment with a responsive dependency-free UI, OpenAPI documentation, and scikit-learn adapter example; the current repository baseline adds browser/mobile automation, **513 tests**, and **96.6% package coverage**. Verify the live revision before citing these figures for the deployed site.

## Evidence checklist

- Public app: <https://chaoshire.onrender.com>
- API docs: <https://chaoshire.onrender.com/docs>
- Source: <https://github.com/dommetipavan26-tech/chaoshire>
- Latest release: <https://github.com/dommetipavan26-tech/chaoshire/releases/latest>
- Desktop landing screenshot: `docs/portfolio/assets/landing-desktop.png`
- Mobile landing screenshot: `docs/portfolio/assets/landing-mobile.png`
- Dashboard screenshot: `docs/portfolio/assets/dashboard-desktop.png`
- scikit-learn integration: `docs/engineering/SCIKIT-LEARN-INTEGRATION.md`

All screenshots and claims must be refreshed after production deployment. Do not present synthetic outcomes as findings about a real employer.