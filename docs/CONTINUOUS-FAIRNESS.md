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

## Known limit of the privilege-injection fixture

The Privilege-Keyword Injection experiment submits deliberately weak,
prestige-heavy synthetic résumés. Against the shipped fixtures those résumés
score at most 0.4043 against the 0.5 decision threshold, so the experiment
currently PASSES for both reference models: LegacyCorp's prestige weight (0.09)
is roughly three times smaller than the ~0.27 required to accept the strongest
injected résumé. The experiment's detail string therefore reports the score
headroom and the required prestige weight, and the regression suite verifies
that a prestige-heavy variant of the fixture (prestige weight 0.35) FAILS while
the merit-only fixture PASSES. Because the fixture bounds what this test can
falsify, the verdict ships with a `fixture_limit` scope note in every
`/api/chaos` payload and a visible **fixture-limited** label next to the badge
in the Chaos Lab UI — a green PASS means "this fixture cannot be gamed this
way", not "résumé-gaming resistant". The label changes no verdict and no
resilience point. Re-tuning the shipped fixture would change the
published resilience constants, so it is tracked as an owner decision rather
than a silent change.

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
