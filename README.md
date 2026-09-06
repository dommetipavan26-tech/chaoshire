# ChaosHire

### Chaos testing for fair hiring AI

[Live demo](https://chaoshire.onrender.com) · [API docs](https://chaoshire.onrender.com/docs) · [Development roadmap](PROJECT-ROADMAP.md)

> Netflix breaks its own servers to find weaknesses before customers do. ChaosHire applies the same idea to automated hiring decisions: stress the model safely before unfair behavior affects real candidates.

ChaosHire is an open-source fairness-auditing prototype for hiring models. It combines conventional group-fairness metrics with controlled counterfactual experiments, candidate-level explanations, mitigation simulations, and an appeals workflow.

## Why this project exists

A normal fairness dashboard asks, **“Did groups receive different outcomes?”** ChaosHire also asks, **“Would this exact decision change if only the candidate's identity changed?”**

That second question powers the **Chaos Lab**:

| Test | Controlled experiment | Risk exposed |
|---|---|---|
| Gender-swap counterfactual | Change gender markers; leave qualifications unchanged | Direct or proxy gender influence |
| Name/community swap | Change community signals; preserve the résumé | Name or community discrimination |
| Privilege-keyword injection | Submit deliberately weak, prestige-heavy synthetic résumés | Susceptibility to résumé gaming and class proxies |
| Career-gap stress | Add a career gap to qualified selected candidates | Penalties affecting caregivers and returners |
| Ageing stress | Re-submit selected younger candidates as 50+ | Hidden age penalties |

Each experiment produces a `PASS`, `WARN`, or `FAIL`. Together they form a 0–100 **Chaos Resilience Score**.

## Demonstration results

The built-in demonstration uses a deterministic synthetic population of 1,000 candidates and two transparent reference models:

| Reference model | Purpose | Fairness certificate | Chaos resilience |
|---|---|---:|---:|
| **LegacyCorp Screen v1** | Intentionally biased test fixture | **42 / F** | **30 / 100** |
| **MeritFirst v2** | Merit-based control fixture | **86 / B** | **100 / 100** |

The LegacyCorp fixture produces:

- **16.9%** decision flips under gender swapping
- **11.1%** decision flips under name/community swapping
- **32.7%** newly rejected hires under the ageing stress test
- **42** qualified candidates incorrectly rejected
- A simulated mitigation improvement from **42/F to 83/B**

These are reproducible **synthetic demonstration results**, not findings about a real employer. The model names are fictional.

## Product capabilities

- Group audits for gender, ethnicity/community and age band
- Disparate impact using the four-fifths threshold
- Demographic-parity and equal-opportunity gaps
- Minimum-cell-size warnings for unreliable group comparisons
- Five counterfactual and stress tests in the Chaos Lab
- Candidate-level additive explanations
- Blind-screening, proxy-removal and threshold-calibration simulations
- Candidate decision lookup and appeals workflow
- CSV decision audit without exposing model weights
- Responsive, dependency-free web dashboard

## Architecture

```text
Browser (vanilla HTML/CSS/JS)
             │ JSON/HTTP
             ▼
       FastAPI application
       ├── synthetic reference data
       ├── model scoring
       ├── fairness metrics
       ├── chaos experiments
       ├── explanations
       └── mitigations + appeals
             │
       NumPy + Pandas
```

The current release intentionally keeps the architecture compact for reproducibility. Persistence, authentication, configurable schema mapping, and separated service modules are tracked for later releases.

## Quick start

### Option 1 — Python

```bash
git clone https://github.com/dommetipavan26-tech/chaoshire.git
cd chaoshire
python -m venv .venv

# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
python -m uvicorn backend:app --reload
```

Open <http://localhost:8000>. Interactive API documentation is available at <http://localhost:8000/docs>.

### Option 2 — Docker

```bash
docker build -t chaoshire .
docker run --rm -p 8000:8000 chaoshire
```

### Run tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions runs the same tests on Python 3.11 and 3.12 for every pull request and push to `main`.

## Audit your own decisions

The upload workflow accepts a CSV containing model **outcomes**, so a vendor does not need to expose weights or source code.

Required columns:

```csv
candidate_id,gender,ethnicity,age_band,decision,qualified
C-001,F,G2,36-50,0,1
C-002,M,G1,26-35,1,1
```

- `decision`: accepted values include `1`, `true`, `yes`, and `accepted`
- `qualified`: optional ground-truth label used for equal-opportunity analysis
- At least one supported group column is required

Download a compatible synthetic sample from `/api/sample.csv`.

## Three-minute walkthrough

1. Open **LegacyCorp Screen v1** and note its 42/F certificate.
2. Open **Chaos Lab** and run the suite; explain the 16.9% gender-swap flip rate.
3. Open **Who Got Filtered Out** and show the 42 qualified rejected candidates.
4. Apply all three mitigations and compare 42/F with 83/B.
5. Switch to **MeritFirst v2** to demonstrate that the same tests can certify a cleaner model.
6. In **Appeals**, look up `C-1046`; the system identifies a likely qualified rejection and prioritizes the appeal.

## Methodology and limitations

ChaosHire is an educational and portfolio-grade prototype—not a legal compliance certification service.

- The built-in dataset and models are synthetic.
- Observed disparity is evidence requiring investigation; it does not by itself prove unlawful discrimination.
- The four-fifths threshold is a screening heuristic, not a universal definition of fairness.
- Equal-opportunity analysis depends on trustworthy qualification labels.
- Threshold calibration may create legal or operational concerns and requires expert review.
- The current in-memory upload and appeals state is not suitable for sensitive production data.
- Real deployments require privacy assessment, access controls, encryption, retention policies, monitoring, and legal review.

## Roadmap

- [x] Deterministic reference models and fairness audit
- [x] Counterfactual Chaos Lab
- [x] Explanations, mitigation simulations and appeals
- [x] Public deployment, automated tests and container support
- [ ] Configurable CSV schema and protected attributes
- [ ] Persistent audit history and role-based access
- [ ] Intersectional fairness analysis
- [ ] Downloadable HTML/PDF audit reports
- [ ] Model-version regression gates for CI/CD
- [ ] Pluggable scoring adapters and SHAP explanations

## Responsible use

Do not upload real applicant data to the public demonstration. Use synthetic or properly anonymized data only. ChaosHire should support—not replace—qualified human, statistical, legal and domain review.

## License

Released under the [MIT License](LICENSE).
