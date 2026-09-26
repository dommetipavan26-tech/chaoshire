# ChaosHire statistical methodology

This document describes the statistics shown by the audit API and dashboard. It is written for reproducibility, not as legal advice.

## Selection rate

For group \(g\):

```text
selection_rate(g) = selected_candidates(g) / total_candidates(g)
```

## Disparate impact

```text
disparate_impact = minimum_group_selection_rate / maximum_group_selection_rate
```

ChaosHire marks a ratio below `0.80` as failing the four-fifths screening threshold. This is an investigation trigger, not proof of unlawful discrimination and not a universal definition of fairness.

## Demographic-parity gap

```text
parity_gap = maximum_group_selection_rate - minimum_group_selection_rate
```

The demonstration uses `0.10` as its warning threshold.

## Equal-opportunity gap

When a qualification or ground-truth label is supplied, ChaosHire calculates each group's true-positive rate:

```text
TPR(g) = selected_and_qualified(g) / qualified(g)
equal_opportunity_gap = maximum_TPR - minimum_TPR
```

This metric is only as trustworthy as the supplied ground truth. Historical performance ratings or previous human decisions may themselves contain bias.

## 95% Wilson score interval

Every displayed selection rate and true-positive rate includes a two-sided 95% Wilson score interval. Wilson intervals behave better than the simple normal approximation for small samples and proportions near zero or one.

For observed proportion \(p = x/n\) and \(z = 1.959964\), the interval is:

```text
centre = (p + z²/(2n)) / (1 + z²/n)
margin = z × sqrt(p(1-p)/n + z²/(4n²)) / (1 + z²/n)
interval = centre ± margin
```

An interval describes sampling uncertainty under binomial assumptions. It does not account for dataset shift, measurement error, dependence between records, or biased labels.

## Exploratory significance indicator

For each attribute, ChaosHire compares the groups with the lowest and highest observed selection rates using a two-sided pooled two-proportion z-test.

```text
H0: selection_rate(lowest) = selection_rate(highest)
```

The dashboard labels `p < 0.05` as statistically significant. This indicator is exploratory:

- It does not establish causation or illegality.
- Statistical significance is not the same as practical importance.
- Repeated comparisons increase false-positive risk.
- Formal studies should pre-register comparisons and apply an appropriate multiple-testing correction.
- Very small groups remain visible but are excluded from the highest/lowest comparison when reliable groups are available.

## Minimum group size

The default minimum reliable group size is 30 and can be configured from 2 to 500 for uploaded datasets. Groups below the threshold are marked `low_n`. They remain visible, but ChaosHire excludes them from worst-case aggregation whenever at least one reliable group exists.

This rule prevents tiny cells from dominating the score; it does not make larger cells automatically representative.

## Assessability guards

A fairness risk score is only meaningful when the data actually supports a
between-group comparison. ChaosHire therefore marks an audit **not assessable**
(grade `N/A`, score 0, with explicit reasons) when:

- the dataset is empty;
- every candidate received the same decision (all selected or all rejected), so selection rates carry no information;
- no protected attribute was supplied or detected; or
- no protected attribute has at least two groups above the minimum reliable size.

Without these guards a model that rejects everybody would score a perfect
100/A, because ratios of identical rates are trivially equal. Not-assessable
audits still report their group metrics for inspection, appear as `N/A` in the
dashboard, reports, and audit history, and raise a HIGH finding in the review
agent.

## Intersectional analysis

ChaosHire creates every pairwise combination of selected protected attributes. For example:

```text
gender × age_band
region × disability_status
```

It then applies the same group metrics, confidence intervals, small-cell rules, and exploratory significance test to the combined groups.

Intersectional results are reported separately and **do not alter the Fairness Risk Score**. This prevents the risk score from changing merely because more attributes were supplied and avoids double-counting overlapping evidence.

## Fairness Risk Score

The score uses primary, non-intersectional attributes only, so it does not change
merely because more attributes were supplied.

```
total = measured_points / available_points × 100
```

| Component | Points | Requires |
|---|---:|---|
| Disparate impact (four-fifths rule) | 40 | group selection rates |
| Demographic parity gap | 20 | group selection rates |
| Equal opportunity gap | 25 | ground-truth qualification labels |
| **`available_points` with ground truth (`basis: "full"`)** | **85** | |
| **`available_points` without it (`basis: "selection-rate-only"`)** | **60** | |

Component points scale linearly from the measured gap: disparate impact awards
`40 × min(DI / 0.8, 1)`, parity awards `20 × max(0, 1 − gap / 0.15)`, and equal
opportunity awards `25 × max(0, 1 − gap / 0.2)`. The total is rounded and clamped
to `[0, 100]`, then graded A ≥ 90, B ≥ 75, C ≥ 60, D ≥ 45, otherwise F. An
unassessable audit returns grade `N/A` with `basis: "none"` and
`available_points: 0` rather than a number.

### Nothing is awarded for free

Earlier versions added an unconditional **15 "transparency" points** for
disclosure, release gates, CI and appeal routes. Those are properties of the
ChaosHire platform, not of the model under audit, and none of them were ever
measured: every audited model received the same credit for a feature it does not
own, a transparent but badly biased model scored higher on a *fairness* scale, a
genuinely failing fixture reported 47/D instead of 32/F, and a perfect
group-fairness result was capped at 85. The points are removed. A perfect result
now scores 100/A on merit, and the platform capabilities are still disclosed —
as `platform_disclosure` text carrying `scored: false` and
`included_in_total: false`, with a `why_unscored` explanation.

### The denominator is part of the result

Equal opportunity needs true-positive rates, which need ground-truth
qualification labels. Without them the component is not measured at zero — it is
excluded, and `available_points` drops from 85 to 60. Two scores printed side by
side on different bases are therefore **not** measuring the same thing, and a
higher selection-rate-only score does not mean a fairer model. Every `certificate`
payload states this explicitly:

| Key | Meaning |
|---|---|
| `measured_points`, `available_points`, `scale` | the arithmetic, in full |
| `basis` | `"full"`, `"selection-rate-only"`, or `"none"` |
| `basis_note` | why that basis applies, in prose |
| `unmeasured_components` | label, points forgone, and the reason for each |
| `comparable_with_full_basis` | `false` whenever the score rests on less evidence |
| `platform_disclosure` | disclosed, never scored |

The HTML and PDF reports print the basis next to the number and carry the
comparability warning in the same place, so the disclosure cannot be separated
from the figure it qualifies.

### What the score is not

The score is a transparent ChaosHire product indicator—not an official
certification from a regulator, standards body, or government agency. It does not
establish legal compliance and does not by itself prove or disprove
discrimination. Per-group threshold calibration is deliberately **not** part of
it and not available as a mitigation; see `SECURITY.md` and
[42 U.S.C. § 2000e-2(l)](https://www.law.cornell.edu/uscode/text/42/2000e-2).

## Why a more accurate model can score lower

The fairness risk score and model accuracy measure different things, and a
fitted model optimises only the second. The bundled fixtures show this
directly. Every figure below is computed at runtime by
`chaoshire.training.disparity_diagnostics()` and pinned in
`tests/core/test_trained_model.py`.

| Decisions | Agreement with `qualified` | Accepted | Worst disparate impact | Score |
|---|---:|---:|---:|---:|
| MeritFirst v2 (hand-written) | 87.3% | 459 | 0.873 (age band) | 84/B |
| TalentFit v3 (fitted to the label) | 89.4% | 376 | 0.727 (age band) | 66/C |
| Perfect predictor (accept exactly the qualified) | 100% | 400 | 0.663 (gender) | 68/C |

**Base rates.** Disparate impact and the parity gap compare selection rates
only. When the ground-truth label's positive rate differs between groups, an
accurate model must select those groups at different rates. It then loses
disparate-impact and parity points even though its equal-opportunity gap can be
small. This is the standard incompatibility between demographic parity and
accuracy under unequal base rates; it is not a defect in the model. On this
fixture the base-rate differences are sampling noise: the merit formula never
reads identity, but 1,000 draws give 45% of women, 37% of men and 30% of 57
non-binary candidates a qualified label.

**Selection volume.** Ratios of selection rates narrow as more candidates are
accepted. MeritFirst accepts 459 candidates and TalentFit 376, against 400
qualified. Holding both to the same volume removes most of the gap (MeritFirst at
376 accepted: 75; TalentFit at 459: 73). Compare models at matched acceptance
rates before reading a score difference as a difference in fairness.

**Proxies.** TalentFit is offered college prestige and career gap as candidate
proxies. The label never uses them, so they receive near-zero weight (+0.012 and
+0.030). Zeroing them changes 23 decisions, and refitting without them lowers
the score to 58/D. The four-fifths failure is inherited from the label, not
leaked through proxies. On real data, where proxies can carry signal, this has
to be measured, not assumed; the same diagnostics apply.

**Resilience.** A counterfactual swap can only flip a decision if the model
reads the swapped signal. MeritFirst and TalentFit carry no weight on gender,
community or age, and no penalty for a career gap, so four of their five chaos
experiments pass **by construction**. The `/api/chaos` payload labels them
(`by_construction`, `passes_by_construction`, `resilience_scope`). A 100/100
resilience score shows what a model does not read directly. It is not evidence
of equal outcomes.

Training for accuracy therefore gives no reason to expect a better fairness
score. If the release policy requires one, it has to be an explicit objective or
constraint, and the label has to be audited first, because a model cannot be
fairer than the target it is trained to reproduce without trading away
agreement with that target.
