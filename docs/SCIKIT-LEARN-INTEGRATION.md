# scikit-learn decision-adapter example

`examples/sklearn_decision_adapter.py` shows how to connect ordinary scikit-learn predictions to ChaosHire without uploading model weights or executable model files.

The example:

1. creates 800 deterministic synthetic candidate records using seed `1046`;
2. trains a `StandardScaler` + `LogisticRegression` pipeline;
3. excludes `gender` and `community` from the model features;
4. normalizes predictions to the `DecisionAdapter` contract; and
5. audits the resulting `accepted` decisions by protected attribute.

## Run it

From the repository root:

```bash
python -m pip install -r requirements-examples.txt
python -m examples.sklearn_decision_adapter
```

The output includes the adapter metadata, row count, fairness risk score, disparate impact, and demographic-parity gap. Since the random seed and inputs are fixed, repeated runs produce identical output.

## Adapt it to your model

Return a Pandas `DataFrame` from the provider with:

- required: `accepted` (boolean decision);
- recommended: `candidate_id`, `qualified`, and the protected attributes to audit.

Then wrap the provider:

```python
from chaoshire.adapters import CallableDecisionAdapter

adapter = CallableDecisionAdapter(
    model_id="your-versioned-model-id",
    provider=your_decision_provider,
)
decisions = adapter.decisions()
```

Keep inference inside your controlled environment. ChaosHire consumes normalized outcomes; it does not need proprietary model weights.

## Responsible-use boundary

This synthetic example demonstrates integration mechanics only. A fairness risk score is a screening signal for investigation and human review. It is not legal certification, does not establish compliance, and does not by itself prove or disprove discrimination. Real assessments require context, data-quality review, domain expertise, and applicable legal guidance.

## Compatibility note

The public JSON and Python interfaces retain the historical `certificate` field and `--min-certificate` CLI option for backward compatibility. User-facing documentation calls the same heuristic aggregate a **fairness risk score** to avoid implying independent certification.
