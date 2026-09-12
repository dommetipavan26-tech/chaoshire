# Continuous fairness engineering

ChaosHire treats fairness checks as release tests rather than one-time dashboard reviews.

## Reusable Chaos Test contract

Every test implements the same conceptual interface:

```text
reference data + model → controlled experiment → observation → threshold → verdict + evidence
```

A test returns a normalized rate, human-readable result, details, candidate-level evidence, and evidence count. `PASS`, `WARN`, and `FAIL` thresholds can be configured without changing experiment code.

## Deterministic experiment IDs

A SHA-256 fingerprint of the model name, thresholds, and normalized test rates produces an ID such as:

```text
EXP-2F4A...
```

The same model, policy, and results produce the same ID. Changing policy or model behavior changes the ID, making runs reproducible and comparable without persisting raw candidate rows.

## Candidate-level evidence

Counterfactual and stress tests return the affected synthetic candidate IDs with before/after scores, decisions, and score deltas. API callers can cap evidence from 0–50 records. The public GET endpoint defaults to 10.

Evidence explains *which decisions changed*; it does not itself determine whether discrimination was unlawful.

## Model comparison

```text
GET /api/compare?baseline=legacy&candidate=fair
```

The response compares fairness risk score, chaos resilience, worst disparate impact, acceptance rate, and experiment IDs.

## Fairness release gate

```text
POST /api/gate
```

The gate enforces absolute floors and regression tolerances:

- Minimum fairness risk score
- Minimum chaos resilience
- Minimum worst-case disparate impact
- Maximum risk-score regression
- Maximum resilience regression

A successful candidate returns `PASS`; any failed check returns `BLOCK`.

### Command line

```bash
python -m chaoshire gate \
  --baseline legacy \
  --candidate fair \
  --min-certificate 75 \
  --min-resilience 80 \
  --min-di 0.80
```

The process exits `0` for PASS and `1` for BLOCK, so CI platforms can stop a release. `.github/workflows/fairness-gate.yml` demonstrates this pattern.

The current adapter compares transparent built-in reference models. Production integration requires a scoring adapter or versioned decision datasets; the policy engine itself is model-agnostic.

## HTML reports

```text
GET /api/report.html?model=legacy&dataset=demo
python -m chaoshire report --model legacy --output report.html
```

Reports contain inline CSS, no JavaScript, and no external assets. They can be downloaded, opened offline, printed, or converted to PDF by a browser. Reports contain aggregate evidence; uploaded reports do not contain raw candidate rows.
