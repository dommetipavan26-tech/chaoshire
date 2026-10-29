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
prestige-heavy synthetic résumés. It currently PASSES for **all three** bundled
variants: the highest injected score is 0.4043 for `legacy`, 0.1997 for `fair`
and 0.0918 for `trained`, all below the 0.5 decision threshold. LegacyCorp's
prestige weight (0.09) would need to reach at least 0.19 on this fixture before
the experiment could fail; MeritFirst and TalentFit apply no prestige weight.
The experiment's detail string reports each variant's score headroom and
required prestige weight. The regression suite verifies that a prestige-heavy
variant (prestige weight 0.35) FAILS while the merit-only fixture PASSES. Because the fixture bounds what this test can
falsify, the verdict ships with a `fixture_limit` scope note in every
`/api/chaos` payload and a visible **fixture-limited** label next to the badge
in the Chaos Lab UI — a green PASS means "this fixture cannot be gamed this
way", not "résumé-gaming resistant". The label changes no verdict and no
resilience point. Re-tuning the shipped fixture would change the
published resilience constants, so it is tracked as an owner decision rather
than a silent change.

## Passes that hold by construction

Some PASS verdicts cannot fail for a given model. A gender or community swap
cannot flip a model that assigns no weight to those signals. Adding a career gap
cannot reject anyone under a model whose gap weight is zero or positive. Moving a
candidate into the 50+ band cannot hurt a model with no age penalty. Each chaos
result therefore carries a model-dependent `by_construction` note (empty when the
test can genuinely fail), and the suite reports `passes_by_construction` and a
`resilience_scope` sentence. The Chaos Lab shows a **by construction** chip and
scope note next to the badge. On the shipped fixtures, MeritFirst and TalentFit
each have four such passes and LegacyCorp has none. Like the fixture-limited
label, this changes no verdict and no resilience point. It stops a 100/100 score
from being read as evidence of equal outcomes, which the fairness risk score
measures separately (the original TalentFit v3 had 100/100 resilience and
scored 66/C).

## Candidate-level evidence

Counterfactual and stress tests return the affected synthetic candidate IDs with before/after scores, decisions, and score deltas. API callers can cap evidence from 0–50 records. The public GET endpoint defaults to 10.

Evidence explains *which decisions changed*; it does not itself determine whether discrimination was unlawful.

## Model comparison

```text
GET /api/compare?baseline=legacy&candidate=fair
```

The response compares fairness risk score, chaos resilience, worst disparate impact, acceptance rate, and experiment IDs. The same endpoint accepts `candidate=trained`; the CI gate compares the current TalentFit v4 reference with `legacy`.

## Fairness release gate

```text
POST /api/gate
```

The gate enforces demo-fixture floors, regression tolerances, and limits over a
**frozen 100-population synthetic holdout**: 50 baseline seeds (51–100) plus ten
populations for each of five evaluation-only stress scenarios (seeds 101–110).
The stress scenarios are kept separate from policy selection. The response reports
mean, p10/p90, bootstrap intervals for population means, per-scenario summaries,
four-fifths pass rate, and sensitivity to five score-space perturbations of the
single global cutoff.

In addition to the existing risk-score, resilience, demo-disparate-impact, and
synthetic-label accuracy checks, the default holdout limits are:

- Mean accuracy ≥0.78 and p10 accuracy ≥0.70
- Mean recall ≥0.90 and p10 recall ≥0.80
- Mean false-positive rate ≤0.40 and p90 false-positive rate ≤0.50
- p10 worst disparate impact ≥0.55 and four-fifths pass rate ≥0.25

The API/CLI/UI let operators state different limits explicitly. They are
synthetic demonstration guardrails, not real-world thresholds, legal findings,
or production-readiness evidence. A successful candidate returns `PASS`; any
failed check returns `BLOCK`.

### Command line

```bash
python -m chaoshire gate \
  --baseline legacy \
  --candidate trained \
  --min-certificate 75 \
  --min-resilience 80 \
  --min-di 0.80 \
  --min-accuracy 0.80 \
  --min-holdout-mean-accuracy 0.78 \
  --min-holdout-p10-di 0.55 \
  --max-holdout-p90-fpr 0.50

python -m chaoshire train --robust-holdout
python -m chaoshire train --calibration-study  # build-time; requires scikit-learn
python -m chaoshire train --policy-study --max-mean-fpr 0.32 --min-mean-recall 0.95
```

The gate process exits `0` for PASS and `1` for BLOCK, so CI platforms can stop a release. The policy-study command reports a Pareto frontier and applies optional utility bounds before selecting an operating point. `.github/workflows/fairness-gate.yml` demonstrates the gate pattern.

The current adapter compares transparent built-in reference models. Production integration requires a scoring adapter or versioned decision datasets; the policy engine itself is model-agnostic.

## HTML reports

```text
GET /api/report.html?model=legacy&dataset=demo
python -m chaoshire report --model legacy --output report.html
```

Reports contain inline CSS, no JavaScript, and no external assets. They can be downloaded, opened offline, printed, or converted to PDF by a browser. Reports contain aggregate evidence; uploaded reports do not contain raw candidate rows.
