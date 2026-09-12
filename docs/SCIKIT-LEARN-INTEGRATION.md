# Integrating an external model: scikit-learn example

ChaosHire audits **decisions**, not model internals. That distinction is the whole
integration story: a vendor or an internal team can keep their weights, their training
pipeline and their data private, and still be auditable.

The runnable example in [`examples/scikit_learn_adapter.py`](../examples/scikit_learn_adapter.py)
proves the claim end-to-end with a real `scikit-learn` pipeline instead of the built-in
transparent fixtures.

```bash
python -m pip install -r requirements-examples.txt
python -m examples.scikit_learn_adapter          # human-readable run
python -m examples.scikit_learn_adapter --json   # machine-readable run
python -m examples.scikit_learn_adapter --strict # exit 1 when a model must be blocked
```

## What the example does

| Step | Code | Result |
|---|---|---|
| 1. Synthesise a population | `synthetic_population()` | 800 fictional applicants, seed `1046` |
| 2. Train two real models | `train_and_decide()` | `StandardScaler` + `LogisticRegression` |
| 3. Normalise to the contract | `to_adapter()` | `CallableDecisionAdapter` satisfying `DecisionAdapter` |
| 4. Audit the decisions | `chaoshire.metrics.audit` | group + intersectional metrics, Wilson intervals |
| 5. Seal the evidence | `build_evidence_bundle()` | SHA-256 digest, verified before use |
| 6. Evaluate a release policy | `release_policy()` | per-check PASS/FAIL and a blocking list |

No real applicant data is used, and none is accepted: the generative process is written
down in the docstring of `synthetic_population()` so the example can be reviewed, refuted,
or replaced.

## The synthetic setup, deliberately

`ability` is the hidden truth. The label `qualified` depends on `ability` only. But two
*observed* signals are contaminated by things that are not merit:

- measured **skills** absorb a coaching/wealth effect that runs through `prestige`;
- a **career gap** depresses the measured test score although ability is unchanged.

So a "naive" model that reads résumé presentation (`skills, experience, education, certs,
prestige, gap`) can be *more accurate* than a "blind" model and still fail the fairness
gate. That is the point of auditing decisions rather than model cards.

## Reference output

Deterministic on seed `1046` with `scikit-learn 1.5+`:

```text
Synthetic population: 800 applicants · seed 1046 · no real applicant data

  sklearn-resume-naive
    Fairness Risk Score     78 / B
    accept rate / accuracy  45.1% / 92.4%
    qualified rejected      30
    worst DI / parity / TPR 0.8679 / 0.0624 / 0.1056
    evidence                sha256:001be23000ef70d0… verified=True
    release policy          FAIL → release blocked
      [pass] Fairness Risk Score >= 75 (actual 78)
      [pass] Worst disparate impact >= 0.8 (actual 0.8679)
      [pass] Demographic parity gap <= 0.1 (actual 0.0624)
      [FAIL] Equal-opportunity gap <= 0.1 (actual 0.1056)
      [pass] Accuracy >= 0.7 (actual 0.9237)

  sklearn-blind-merit
    Fairness Risk Score     80 / B
    accept rate / accuracy  44.5% / 90.2%
    qualified rejected      41
    worst DI / parity / TPR 0.8414 / 0.0726 / 0.0823
    evidence                sha256:6fe47137b88a5400… verified=True
    release policy          PASS → release approved
```

Read the trade-off honestly: the blind model releases, but it also rejects **11 more truly
qualified candidates** in this synthetic population and loses ~2 points of accuracy. Fairness
work is not a free lunch, which is why ChaosHire reports utility next to fairness and keeps
candidate-level evidence for appeals rather than stopping at a single score.

## The contract you actually implement

`chaoshire/adapters.py` defines the whole surface:

```python
class DecisionAdapter(Protocol):
    adapter_id: str

    def describe(self) -> dict[str, Any]: ...
    def decisions(self) -> pd.DataFrame: ...
```

One required output column:

| Column | Meaning |
|---|---|
| `accepted` | the decision the model actually made (1/0 or any values you normalise to them) |

Recommended extras: `candidate_id`, `qualified` (ground truth, enables equal-opportunity
analysis), and the protected attribute columns you want audited.

Three integration modes ship with the package and are listed by `GET /api/adapters`:

| Adapter | Use |
|---|---|
| `ReferenceModelAdapter` | the deterministic LegacyCorp / MeritFirst fixtures |
| `CallableDecisionAdapter` | in-process provider callback — what the scikit-learn example uses |
| `csv-decisions` | `POST /api/upload` for teams that only export decision logs |

## Pointing it at your own model

Replace step 1 and reuse everything after it:

```python
from chaoshire.metrics import audit
from chaoshire.evidence import build_evidence_bundle
from chaoshire.adapters import CallableDecisionAdapter

frame = my_production_export()           # candidate_id, accepted, gender, age_band, …
adapter = CallableDecisionAdapter(model_id="screen-v7", provider=lambda: frame)
audited = audit(adapter.decisions(), ["gender", "age_band"])
bundle = build_evidence_bundle(audited)  # SHA-256 sealed, aggregate metrics only
```

If your stack is not Python, emit the same CSV shape and use `POST /api/upload` — the audit
does not care which library produced the outcome.

## Limits of this example

- Synthetic data illustrates a mechanism; it is not evidence about any real employer.
- A `Fairness Risk Score` prioritises review. It is not a legal certification and does not,
  on its own, prove or disprove unlawful discrimination.
- A linear model with four to six features was chosen so the audit numbers can be reasoned
  about; gradient-boosted or LLM-based screeners integrate the same way, but their disparities
  need the same metric scrutiny.
- Groups below the minimum reliable size are flagged rather than silently dropped, so small
  subgroups can produce noisy but honest intervals.
