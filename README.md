# ChaosHire

### Chaos testing for fair hiring AI

[Live demo](https://chaoshire.onrender.com) · [API docs](https://chaoshire.onrender.com/docs) · [Privacy Policy](chaoshire/web/privacy.html) · [Terms](chaoshire/web/terms.html) · [scikit-learn example](docs/engineering/SCIKIT-LEARN-INTEGRATION.md) · [Portfolio evidence](docs/portfolio/PORTFOLIO-EVIDENCE.md) · [Case study](docs/portfolio/PORTFOLIO-CASE-STUDY.md) · [Architecture](docs/engineering/ARCHITECTURE.svg) · [Methodology](docs/engineering/METHODOLOGY.md) · [Platform](docs/portfolio/PORTFOLIO-PLATFORM.md) · [Monitoring](docs/operations/MONITORING.md) · [Roadmap](docs/planning/PROJECT-ROADMAP.md)

> Netflix breaks its own servers to find weaknesses before customers do. ChaosHire applies the same idea to automated hiring decisions: stress the model safely before unfair behavior affects real candidates.

![ChaosHire landing page showing LegacyCorp, MeritFirst, and TalentFit (trained) model choices](docs/portfolio/assets/landing-desktop.png)

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

On the shipped fixtures the privilege-keyword injection verdict is labelled
**fixture-limited** (in the API payload, next to the badge in the Chaos Lab, and
in `docs/engineering/CONTINUOUS-FAIRNESS.md`): those résumés cannot clear the decision
threshold at the fixtures' prestige weight, so the PASS records how much
headroom exists rather than general resistance to résumé gaming. The label
changes no verdict and no resilience point.

Passes that **cannot fail** for the model under test are labelled **by
construction** in the same way. If a model carries no weight on gender markers,
a gender swap cannot change a single score, so its PASS shows the model does not
read gender directly. It says nothing about whether groups receive equal
outcomes. MeritFirst and TalentFit each have four such passes. Every
`/api/chaos` payload reports `by_construction` per test plus
`passes_by_construction` and a `resilience_scope` sentence for the suite. These
labels change no verdict and no resilience point either.

## Demonstration results

The built-in demonstration uses a deterministic synthetic population of 1,000 candidates and **three selectable model variants**. `legacy` and `fair` are hand-authored scoring fixtures; `trained` is fitted with scikit-learn at build time and loaded from a pinned artifact at runtime (no scikit-learn runtime dependency).

| Model (API/CLI ID) | Purpose | Fairness risk score | Chaos resilience |
|---|---|---:|---:|
| **LegacyCorp Screen v1** (`legacy`) | Intentionally biased test fixture | **32 / F** | **30 / 100** |
| **MeritFirst v2** (`fair`) | Merit-based control fixture | **84 / B** | **100 / 100** |
| **TalentFit v3 (trained)** (`trained`) | Logistic regression on merit features with a cost-sensitive cutoff; protected attributes and proxies withheld | **80 / B** | **100 / 100** |

All three appear in the dashboard's model selector. With the app running locally, audit each variant by its ID:

```bash
curl 'http://localhost:8000/api/audit?model=legacy&dataset=demo'
curl 'http://localhost:8000/api/audit?model=fair&dataset=demo'
curl 'http://localhost:8000/api/audit?model=trained&dataset=demo'
```

The LegacyCorp fixture produces:

- **16.9%** decision flips under gender swapping
- **11.1%** decision flips under name/community swapping
- **32.7%** newly rejected hires under the ageing stress test
- **42** qualified candidates incorrectly rejected
- A simulated mitigation improvement from **32/F to 80/B** using blind screening plus proxy removal

TalentFit v3 is the model we actually trained, and the most instructive one
because its first version failed. Its coefficients are pinned in
`chaoshire/artifacts/trained_model.json` with a SHA-256 digest;
`python -m chaoshire train --check` re-derives them and fails CI if they drift
(agreement floor 0.90).

### How TalentFit v3 was upgraded

The **original v3** was a logistic regression fitted to the `qualified` label,
kept college prestige and career gap as inputs, and accepted at probability 0.5.
It was the **most accurate** model (89.4% agreement with the label), yet it
scored **66/C** and failed the four-fifths rule (worst disparate impact 0.727,
age band). "Trained" does not mean "fairer": the fit optimises agreement with
the label, and on this fixture the label itself is uneven across groups.
`qualified` is built only from skills, experience, education and certifications,
all drawn independently of identity, but with 1,000 candidates the groups end
up with different qualified rates by chance (45% of women, 37% of men, 30% of
the 57 non-binary candidates). A **perfect predictor** of the label scores
**68/C**, so any model that copies the label closely inherits the gap.

The **upgraded v3** changes two things, both fixed on product grounds before
looking at the audit:

1. **Proxy-free inputs.** Prestige and career gap are dropped, following the
   platform's own proxy-removal mitigation. The label never uses them; the
   original fit weighted them near zero (and gave career gaps a meaningless
   *positive* weight). The artifact loader now rejects any proxy weight.
2. **A cost-sensitive cutoff.** A first-round screen that wrongly rejects a
   qualified candidate loses them for good; a wrongly advanced one is caught at
   interview. Treating a false rejection as **2×** as costly as a false
   acceptance gives the standard Bayes-optimal cutoff P(qualified) ≥ 1/(1+2) =
   **1/3**. It is **one cutoff for every candidate**, never a per-group
   threshold (see the § 2000e-2(l) note below). The policy is recorded in the
   artifact as `decision_policy`.

| On the fixture | MeritFirst v2 | Original v3 | **Upgraded v3** |
|---|---:|---:|---:|
| Fairness risk score | **84 / B** | 66 / C | **80 / B** |
| Worst disparate impact (four-fifths ≥ 0.8) | 0.873 ✓ | 0.727 ✗ | **0.814 ✓** |
| Qualified candidates wrongly rejected (of 400) | 34 | 65 | **21** |
| Recall on qualified candidates | 91.5% | 83.8% | **94.8%** |
| Accuracy vs `qualified` | 87.3% | **89.4%** | 87.6% |

**Does it generalise?** Every model was fitted or written against one fixture,
so its fixture score can flatter it. `python -m chaoshire train --holdout`
re-draws 49 whole populations from the same generator with other seeds and
audits the unchanged coefficients on each:

| On 49 unseen populations (mean) | MeritFirst v2 | Original v3 | **Upgraded v3** |
|---|---:|---:|---:|
| Fairness risk score | 74.4 | 69.5 | **76.0** |
| Qualified candidates wrongly rejected | 23.9 | 53.4 | **18.1** |
| Recall on qualified candidates | 94.0% | 86.7% | **95.5%** |
| Accuracy | 85.7% | **88.6%** | 85.0% |

All three means were re-derived after the equal-opportunity gap started
excluding groups with too few *qualified* people to estimate a true-positive
rate from; each model moved up by about two points and the ranking is unchanged
(see [METHODOLOGY.md](docs/engineering/METHODOLOGY.md#minimum-group-size)).
Fixture scores, accuracy, recall and the rejection counts above are unaffected.

**The trade-offs, stated plainly.** The upgrade buys fairness and recall with
precision. It advances more candidates to interview (482 vs 459 for
MeritFirst), and out of sample it is slightly less accurate than MeritFirst.
On the audited fixture MeritFirst still scores 4 points higher (84 vs 80). The
cutoff was not tuned to close that gap. A 3× cost scores 85, one point above MeritFirst,
but choosing a threshold because it wins on the audited sample is exactly the
gaming this project exists to catch: the fixture score is noisy and not even
monotonic in the cutoff (58, 55, 65, 76 from probability 0.50 down to 0.35),
while the unseen-population mean rises smoothly (69.2, 72.0, 74.7, 75.9). The release gate agrees: it now passes LegacyCorp → TalentFit (the
original v3 was blocked) and blocks MeritFirst → TalentFit on the 4-point
regression. Resilience 100/100 holds **by construction** for both MeritFirst and
TalentFit: a model with no protected inputs cannot flip on a swap.

All of this is computed at runtime without scikit-learn by
`chaoshire.training.disparity_diagnostics()` and `holdout_comparison()`, served
in step 7 of the guided demo (`/api/demo`), and pinned by
`tests/core/test_trained_model.py`. See
[METHODOLOGY.md](docs/engineering/METHODOLOGY.md#why-a-more-accurate-model-can-score-lower).

These are reproducible **synthetic demonstration results**, not findings about a real employer. The model names are fictional.

> **Responsible-use boundary:** The fairness risk score is a transparent heuristic for investigation and human review. It is not an independent certification, does not establish legal compliance, and does not by itself prove or disprove discrimination. The public API retains the historical `certificate` JSON key and `--min-certificate` CLI option for backward compatibility.

### How the score is computed

`total = measured / available × 100` over group-fairness components only:

| Component | Points |
|---|---:|
| Disparate impact (four-fifths rule) | 40 |
| Demographic parity gap | 20 |
| Equal opportunity gap | 25 |
| **Available when the equal-opportunity gap is measurable** | **85** |
| **Available when it is not** — no qualification labels, or no two groups hold enough qualified people | **60** |

Two properties follow, and both are stated in every `certificate` payload rather
than left for a reader to infer:

- **Nothing is awarded for free.** Earlier versions added an unconditional 15
  "transparency" points for disclosure, release gates, CI and appeal routes.
  None of that is a property of the model under audit and none of it was ever
  measured, so it gave a badly biased model 47/D instead of 32/F and capped a
  perfect one at 85. Those points are gone; a perfect group-fairness result now
  scores 100/A on merit. The platform capabilities are still disclosed — as
  `platform_disclosure` text, with `scored: false`.
- **The denominator is part of the result.** `basis` is `"full"` (85 available
  points) or `"selection-rate-only"` (60), `available_points` and
  `measured_points` are reported, `unmeasured_components` names what could not
  be measured and why, and `comparable_with_full_basis` is `false` whenever the
  score rests on less evidence. A 60-point-basis score must not be ranked
  against an 85-point-basis score; the HTML and PDF reports say so in the same
  place they print the number.

## Product capabilities

- Group audits for gender, ethnicity/community and age band
- Disparate impact using the four-fifths threshold
- Demographic-parity and equal-opportunity gaps
- 95% Wilson confidence intervals for selection and true-positive rates
- Exploratory highest-vs-lowest two-proportion significance tests
- Pairwise intersectional audits such as gender × age band
- Minimum-cell-size warnings for unreliable group comparisons, applied to a group's rows **and** to the qualified people behind its true-positive rate
- Strict reference-model and dataset validation: unknown identifiers return HTTP 400, never a substituted audit
- Explicit "not assessable" verdicts when decisions show no variation or groups are too small to compare
- Reusable counterfactual and stress-test framework with configurable thresholds
- Deterministic experiment IDs and candidate-level before/after evidence
- Side-by-side model-version comparison and automated CI/CD fairness release gate
- Deterministic evidence-grounded fairness review with prioritized human actions (a transparent rules engine — not an AI agent or language model)
- Pluggable decision-adapter contract for reference, CSV, and production providers
- Tamper-evident SHA-256 evidence bundles with verification API and CLI
- Self-contained HTML reports plus dependency-free native PDF summaries
- API-key write protection, request-size limits, separate read and write rate limits, a nonce-based Content-Security-Policy, a bounded appeal queue, and operational metrics
- Accessible mobile/PWA shell and a stable three-minute guided portfolio demo
- Candidate-level additive explanations
- Blind-screening and proxy-removal simulations, plus a research-only per-group threshold contrast that is refused by default and cites [42 U.S.C. § 2000e-2(l)](https://www.law.cornell.edu/uscode/text/42/2000e-2)
- Candidate decision lookup and appeals workflow
- Configurable CSV audits without exposing model weights
- Custom decision, qualification, candidate-ID, and protected-attribute columns
- Configurable favorable values and minimum reliable group size
- Downloadable JSON audit evidence
- Named audit IDs and SQLite-backed aggregate audit history
- Privacy-conscious storage: uploaded candidate rows are never written to history
- Responsive, dependency-free web dashboard

## Architecture

[View the architecture diagram](docs/engineering/ARCHITECTURE.svg).

```text
Browser (vanilla HTML/CSS/JS)
             │ JSON/HTTP
             ▼
      FastAPI route layer
             │
     Application services
      ├── fairness metrics
      ├── chaos experiments
      ├── explanations
      ├── mitigations
      └── appeals / uploads
             │
 Reference models + synthetic data
             │
       NumPy + Pandas
```

### Repository layout

```text
backend.py                 # stable uvicorn backend:app compatibility entry point
chaoshire/                 # importable application; existing module paths stay stable
├── app.py, schemas.py     # HTTP routes and request contracts
├── services.py, demo.py   # workflows and guided demonstration
├── metrics.py, chaos.py   # fairness calculations and experiments
├── models.py, data.py     # synthetic reference models and fixtures
├── repository*.py         # SQLite and optional PostgreSQL persistence
├── artifacts/             # pinned trained-model fixture
└── web/                   # packaged browser shell (served at /)
    ├── index.html        # semantic markup; legal and 404 pages alongside it
    └── static/            # chaoshire.css, chaoshire.js, licensed font, PWA icons
tests/
├── api/                   # endpoints, uploads, and access controls
├── core/                  # metrics, models, and fairness workflows
├── infrastructure/        # repositories, connectors, and build checks
├── web/                   # HTML/CSS/JS, asset cache, CSP, and escaping
└── browser/               # opt-in Playwright suite
docs/
├── engineering/           # architecture, methodology, integration
├── operations/            # persistence, monitoring, releases
├── portfolio/             # case study, evidence, and screenshots
└── planning/              # roadmap and historical task log
scripts/                   # CI checks, icon/screenshot generators, live probes
examples/                  # runnable decision-adapter example
.github/workflows/         # quality, browser, fairness, security, release CI
```

See the [documentation index](docs/README.md), the [file-by-file inventory](docs/operations/REPOSITORY-INVENTORY.md),
and the [1 October 2026 audit and next updates](docs/operations/REPOSITORY-AUDIT.md)
for individual files, verification scope, and maintenance commands. `backend.py`, dependency manifests, `Dockerfile`, `render.yaml`, and the
standard community files remain at the root for existing deployment and tooling
conventions. The Python modules remain at their public `chaoshire.*` import paths;
the web assets are resolved relative to the package rather than the working
directory.

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

Aggregate audit history defaults to `data/chaoshire.db`. Override it with `CHAOSHIRE_DB_PATH`; see [Persistence & privacy](docs/operations/PERSISTENCE.md). Render's free filesystem is ephemeral, so the public demo's history is not durable across redeploys.

The website has privacy and terms pages, SEO and social-sharing metadata, a small-screen layout, and one primary action: **Start the 3-minute demo**. It uses no tracking cookies. Anonymous, first-party page-view counts are sent only after an explicit analytics opt-in and are available only to a server-side operator; they reset on restart. No operator key is embedded in the browser. The hand-managed live deployment may lag this source revision until the owner deploys it; see [website readiness and page-speed checks](docs/operations/WEBSITE-READINESS.md) for verification, limitations, and deployment steps.

### Run tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q               # API, core, infrastructure, and web tests
```

The optional Playwright suite lives in `tests/browser/`; its install and run
commands are in the [documentation index](docs/README.md). GitHub Actions runs
linting, type checking, the trained-model drift check and the default test suite
on Python 3.11 and 3.12; a separate workflow runs the browser tests. The
quality gate requires at least 90% package coverage; the **current source
baseline**, measured locally, contains **504 tests with 97.1% package coverage**
(the configured source set excludes the synthetic fixture module
`chaoshire/data.py`). The tagged release and live site may lag this revision.

`chaoshire/build_info.py` is the single source of truth for every number the
landing page and this README quote. Version, model count, experiment count and
fixture size are derived from the running package at import time, so they cannot
drift. The test count and coverage figure cannot be derived that way, so
`scripts/check_build_info.py` re-derives both from a real pytest run and fails
the build if `chaoshire/build_info.py` disagrees. `GET /api/meta` serves the
result as `build`, and `chaoshire/web/static/chaoshire.js` renders that payload instead
of hardcoding a version string — the failure mode that once left the landing page advertising
v0.21.0 while the package said v0.22.0.

### Optional integrations and reproducible checks

```bash
# Linux / Python 3.11 development; use requirements-py312.txt for Python 3.12
python -m pip install -c constraints/requirements-py311.txt -r requirements-dev.txt
# Optional PostgreSQL runtime driver (SQLite remains default)
python -m pip install ".[postgres]"
# Optional asset/audit/constraint-generation tools
python -m pip install -r requirements-maintenance.txt
# Fresh-wheel verification after `python -m build`
python scripts/check_distribution.py --wheel dist/chaoshire-*.whl --sdist dist/chaoshire-*.tar.gz \
  --constraints constraints/requirements-py311.txt
```

The [engineering update report](docs/operations/REPOSITORY-AUDIT.md) distinguishes local results from owner-only rollout. Strict decision labels, expiring bounded limiter keys, fixed webhook workers, and fail-closed benchmark input are now implemented. PostgreSQL tests are opt-in (`tests/integration/`) and require an explicit **disposable local** `CHAOSHIRE_TEST_POSTGRES_URL`; they never fall back to a production DSN. CI now exercises PostgreSQL, installed packages, and a non-default-PORT container in addition to its quality matrix. Configuring CI is not proof that its remote run has happened.

### Audit scikit-learn predictions

A runnable example trains a deterministic logistic-regression pipeline on synthetic data, normalizes its predictions through the `DecisionAdapter` contract, and prints group-audit results:

```bash
python -m pip install -r requirements-examples.txt
python -m examples.sklearn_decision_adapter
```

### Audit real-world data (UCI Adult)

The same audit engine runs on a real public benchmark, the 1994 US Census
income data (15,060 held-out people), comparing a naive model, a blind model
with proxies removed, and the true label itself:

```bash
python -m examples.adult_income_audit
```

Headline: even a *perfect* predictor of the real label fails the four-fifths
rule on sex, race and age (51/D), and blinding sex and race made the age gap
worse until age was removed too. Full results, trade-offs and a limitation this
audit uncovered are in [REAL-DATA-AUDIT.md](docs/engineering/REAL-DATA-AUDIT.md).

See the [scikit-learn integration guide](docs/engineering/SCIKIT-LEARN-INTEGRATION.md) for the data contract, adaptation steps, and responsible-use limits.

### Continuous fairness commands

```bash
# exits 0 when the candidate passes, 1 when the release must be blocked
python -m chaoshire gate --baseline legacy --candidate fair \
  --min-certificate 75 --min-resilience 80 --min-di 0.80

# self-contained HTML report
python -m chaoshire report --model legacy --output chaoshire-report.html

# native PDF summary
python -m chaoshire report --model legacy --format pdf --output chaoshire-report.pdf

# deterministic fairness review and tamper-evident evidence bundle
python -m chaoshire review --model legacy
python -m chaoshire evidence --model legacy --output chaoshire-evidence.json
```

The gate example compares `legacy` with `fair`; it is not the full model list.
Use `--candidate trained` to evaluate the third variant: LegacyCorp → TalentFit
passes, while MeritFirst → TalentFit is blocked by the 4-point score
regression. `python -m chaoshire train --holdout` prints the unseen-population
comparison. The `report`, `review`, and `evidence` commands accept
`--model legacy`, `--model fair`, or `--model trained`.

See [Continuous fairness engineering](docs/engineering/CONTINUOUS-FAIRNESS.md) for the test contract, experiment fingerprints, evidence format, comparison API, and CI policy.

## Audit your own decisions

The upload workflow accepts a CSV containing model **outcomes**, so a vendor does not need to expose weights or source code.

The minimum input is one outcome column and one group attribute. Their names and values are configurable in the UI or API:

```csv
person_id,region,disability_status,outcome,job_ready
A-001,north,no,advance,qualified
A-002,south,yes,reject,qualified
```

For this example, configure:

- Decision column: `outcome`
- Favorable value: `advance`
- Qualification column: `job_ready` (optional; enables equal-opportunity analysis)
- Qualified value: `qualified`
- Protected attributes: `region, disability_status`
- Minimum reliable group size: `30` by default, configurable from 2–500

Column names are normalized for surrounding whitespace and case. Missing group values are retained as a visible `(missing)` group instead of silently discarded. High-cardinality fields that look like identifiers are rejected as protected attributes. Each successful upload returns its interpretation settings, warnings, and aggregate audit. **Anonymous uploads are not published or persisted** (`published: false`, `audit_id: null`); the dashboard's **Download JSON audit** button downloads that exact browser-local result. Only operator-authenticated uploads populate shared history and the latest-upload slot. `/api/audit/export`, HTML/PDF reports, and evidence endpoints refer to that **shared published slot**, not to an anonymous visitor's upload. See [persistence and privacy](docs/operations/PERSISTENCE.md).

The original schema remains backward-compatible. Download a compatible synthetic sample from `/api/sample.csv`.

## Three-minute walkthrough

1. Open **LegacyCorp Screen v1** and note its **32/F** risk score — and the scoring-basis line beside it, which says the score is 27.1 of 85 available points measured.
2. Open **Chaos Lab** and run the suite; explain the 16.9% gender-swap flip rate.
3. Open **Who Got Filtered Out** and show the 42 qualified rejected candidates.
4. Apply both mitigations and compare **32/F with 80/B**. Note the panel explaining why per-group threshold "calibration" is *not* one of them, with the statute cited.
5. Switch to **MeritFirst v2** (**84/B**, resilience 100/100) to show a cleaner synthetic fixture under the same tests; these results are not a certification.
6. Switch to **TalentFit v3** (**80/B**, resilience 100/100, worst disparate impact 0.814). Its first version was the most accurate model and still scored 66/C, because it copied group gaps already in its training label (a perfect copy of the label scores 68/C). The upgrade drops the proxy features and uses one cost-sensitive cutoff for everyone: it passes the four-fifths rule and wrongly rejects 21 qualified candidates against MeritFirst's 34. Its passes are labelled *by construction*: with no protected inputs it cannot flip on a swap.
7. In **Appeals**, look up `C-1046`; the system identifies a likely qualified rejection and prioritizes the appeal.

## Methodology and limitations

ChaosHire is an educational and portfolio-grade prototype—not a legal compliance certification service.

- The built-in dataset and models are synthetic.
- Observed disparity is evidence requiring investigation; it does not by itself prove unlawful discrimination.
- The four-fifths threshold is a screening heuristic, not a universal definition of fairness.
- Equal-opportunity analysis depends on trustworthy qualification labels.
- Per-group threshold calibration is **not offered as a mitigation**. Setting different cutoff scores by race, colour, religion, sex or national origin in an employment test is an unlawful employment practice under [42 U.S.C. § 2000e-2(l)](https://www.law.cornell.edu/uscode/text/42/2000e-2) (Civil Rights Act of 1991). ChaosHire can still compute it as a labelled research contrast — `threshold_contrast_acknowledged=true`, refused otherwise, reported under its own key and never merged into a mitigation result — but nothing here is legal advice.
- The current in-memory upload and appeals state is not suitable for sensitive production data.
- The public demonstration keeps a single shared slot for **operator-published** uploads, so the latest published aggregate result is readable by every visitor. Anonymous uploads do not replace that slot; their parsed rows are discarded after the response. Published raw rows stay in process memory only.
- Real deployments require privacy assessment, access controls, encryption, retention policies, monitoring, and legal review.

## Roadmap

- [x] Deterministic reference models and fairness audit
- [x] Counterfactual Chaos Lab
- [x] Explanations, mitigation simulations and appeals
- [x] Public deployment, automated tests and container support
- [x] Configurable CSV schema and protected attributes
- [x] Statistical uncertainty and pairwise intersectional fairness analysis
- [x] Named SQLite-backed aggregate audit history
- [x] Model-version comparison and regression gates for CI/CD
- [x] Self-contained HTML and native PDF report export
- [x] Deterministic evidence-grounded fairness review and verified evidence bundles
- [x] Pluggable decision-source adapters
- [x] Optional API-key protection, platform safeguards, metrics, PWA, and guided demo
- [x] Authenticated remote REST connector and SHAP-compatible explanations
- [x] Optional PostgreSQL repository adapter (SQLite remains the default)
- [ ] User accounts, role-based access, and a configured durable deployment

## Responsible use

Do not upload real applicant data to the public demonstration. Use synthetic or properly anonymized data only. ChaosHire should support—not replace—qualified human, statistical, legal and domain review.

## License

Released under the [MIT License](LICENSE).
