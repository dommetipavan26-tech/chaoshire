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
equal_opportunity_gap = maximum_TPR - minimum_TPR   over the reliable groups
```

A group is *reliable* for this metric only when it holds at least
`minimum_group_size` rows **and** at least `minimum_group_size` qualified rows;
see [Minimum group size](#minimum-group-size). Groups that fail the
qualified-count check keep their own TPR and interval in the report but are
excluded from the gap, and the exclusion is published as `eq_opp_excluded` and
`eq_opp_note`. If fewer than two groups remain, the gap is `null` and the
component is dropped from the score rather than computed from one noisy cell.

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

**The same minimum applies to the qualified count.** A true-positive rate's
denominator is the qualified people inside a group, not the group's size, so a
cell can clear `low_n` and still be far too thin to compare. The UCI Adult audit
found exactly that: the Amer-Indian-Eskimo cell has 149 rows but **19** qualified
people, giving a true-positive rate with a Wilson 95% interval of 0.15–0.54, and
the `Other` cell has 122 rows with **24** qualified. ChaosHire's own fixture has
the same shape (57 non-binary candidates, 17 qualified).

Each group therefore reports two independent flags:

| Field | Bounds | Used by |
|---|---|---|
| `n`, `low_n` | rows in the group | disparate impact, parity gap, the significance test |
| `qualified_count`, `low_qualified_n` | qualified rows in the group | the equal-opportunity gap |

A group with `low_qualified_n: true` stays in the report — its rate, interval and
row count are still printed, flagged — but does not enter the equal-opportunity
gap. Selection-rate metrics are untouched, because those are estimated from the
whole group.

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
| Equal opportunity gap | 25 | ground-truth qualification labels, and at least two groups holding `minimum_group_size` qualified people |
| **`available_points` when the gap is measurable (`basis: "full"`)** | **85** | |
| **`available_points` when it is not (`basis: "selection-rate-only"`)** | **60** | |

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
qualification labels — and enough qualified people per group for those rates to
mean anything. When either is missing the component is not measured at zero; it
is excluded, and `available_points` drops from 85 to 60. Two scores printed side
by side on different bases are therefore **not** measuring the same thing, and a
higher selection-rate-only score does not mean a fairer model. The two reasons
are worded differently in the payload — "no ground-truth qualification labels"
versus "no group has enough qualified people for a reliable true-positive rate" —
because they are different findings. Every `certificate` payload states this
explicitly:

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

## Fairness-prioritised model update and its trade-offs

The fairness risk score and accuracy measure different things. TalentFit v4
changes the global decision cutoff to prioritise more equal selection rates and
fewer missed qualified candidates, while explicitly reporting the resulting
accuracy and false-positive trade-off. Every figure is reproducible with
`python -m chaoshire train --policy-study` or `--holdout`, and pinned in
`tests/core/test_trained_model.py`.

| Model decisions on the 1,000-row fixture | Agreement with `qualified` | Accepted | Qualified rejected | Worst disparate impact | Score |
|---|---:|---:|---:|---:|---:|
| MeritFirst v2 (hand-written) | 87.3% | 459 | 34 | 0.873 (age band) | 84/B |
| Original v3 (proxies kept, cutoff 0.5) | 89.4% | 376 | 65 | 0.727 (age band) | 66/C |
| Previous TalentFit v3 (merit only, cutoff 1/3) | 87.6% | 482 | 21 | 0.814 (age band) | 80/B |
| **TalentFit v4 (merit only, cutoff 1/4)** | **83.1%** | **547** | **11** | **0.874 (gender)** | **85/B** |
| Perfect predictor (accept exactly the qualified) | 100% | 400 | 0 | 0.663 (gender) | 68/C |

**The label is still limited.** Disparate impact and parity compare selection
rates. The fixture's merit formula never reads identity, but 1,000 random draws
give different qualified-label rates (45% of women, 37% of men, and 30% of the
57 non-binary candidates). Even a perfect predictor of that label scores 68/C.
That is a synthetic sampling effect—not evidence about a real population—and a
model trained to reproduce the label can inherit its group differences.

**Global cutoff selection.** A wrongly rejected qualified candidate is lost at
this first screen, while a wrongly advanced candidate receives human review.
With false-rejection cost *k* times false-acceptance cost, the Bayes-optimal
probability cutoff is P(qualified) ≥ 1/(1+*k*). TalentFit v4 uses **one global
cutoff**, never per-group thresholds (42 U.S.C. § 2000e-2(l)). Unlike v3's
2:1 cutoff, v4's 3:1 operating point was selected by a documented, synthetic
policy study: compare the fixed candidate grid below on 49 tuning populations
(seeds 1–50, excluding training fixture seed 29), maximize mean fairness risk
score among candidates with mean accuracy ≥ 0.80, then validate the choice on a
disjoint 50-population holdout (seeds 51–100). The accuracy floor avoids
selecting a near-always-advance rule solely because it narrows selection-rate
gaps. These synthetic costs and outcomes are not estimates or guarantees for
real hiring.

| False-rejection cost *k* | Probability cutoff | Mean score on 49 tuning populations | Mean accuracy | Mean recall | Mean false-positive rate | Meets ≥80% accuracy guardrail? |
|---:|---:|---:|---:|---:|---:|:---:|
| 2.0 | 0.3333 | 76.04 | 85.04% | 95.47% | 21.92% | Yes |
| 2.5 | 0.2857 | 77.63 | 83.02% | 97.16% | 26.41% | Yes |
| **3.0** | **0.2500** | **78.63** | **80.91%** | **98.13%** | **30.58%** | **Yes — selected** |
| 3.5 | 0.2222 | 80.71 | 79.13% | 98.70% | 33.92% | No |
| 4.0 | 0.2000 | 81.65 | 77.53% | 99.05% | 36.81% | No |

The automated release gate also applies a default 80% accuracy floor against
this bundled synthetic label; operators may set it explicitly. That is a
non-degeneracy guard, not a real-world performance estimate or hiring-quality
criterion. The policy study is explicit that a higher fairness score is partly
mechanical: advancing more candidates narrows selection-rate ratios. On the fixture, v4's
accuracy is 83.1% (vs v3's 87.6%), its recall rises to 97.3% (from 94.8%), and
its false-positive rate rises to 26.3% (from 17.2%). The score is a screening
signal for human review, not an objective to maximize without utility limits.

### Independent holdout comparison

`python -m chaoshire train --holdout` compares the frozen models on the 50
synthetic populations with seeds 51–100, disjoint from both the training fixture
and policy-tuning seeds. No model is refit on those populations.

| Mean across 50 holdout populations | MeritFirst v2 | Original v3 | Previous TalentFit v3 | **TalentFit v4** |
|---|---:|---:|---:|---:|
| Fairness risk score | 74.04 | 71.88 | 74.62 | **78.40** |
| Mean worst disparate impact | 0.8103 | 0.7884 | 0.8158 | **0.8343** |
| Worst-DI four-fifths pass rate | 56% | 50% | 68% | **74%** |
| Qualified candidates wrongly rejected | 24.84 | 56.16 | 19.84 | **9.02** |
| Recall on qualified candidates | 93.79% | 85.96% | 95.04% | **97.75%** |
| False-positive rate | 19.72% | 9.93% | 21.61% | **30.18%** |
| Accuracy against synthetic label | 85.68% | **88.42%** | 85.05% | **80.99%** |

On this simulator, v4 has a +3.78-point mean score, +0.0185 mean worst disparate
impact, and +6-point four-fifths pass rate versus v3; it also has about 54.5%
fewer missed qualified rows. The cost is about 4.1 percentage points lower
accuracy and an 8.6-point higher false-positive rate. These are generated
populations from one known process, not independent real-world evidence. Results
must not be generalized to actual applicants or employers.

### Frozen stress holdout, uncertainty, and diagnostics (29 October 2026)

The release gate now evaluates more than the demo fixture. The command
`python -m chaoshire train --robust-holdout` keeps the 50 baseline holdouts (seeds 51–100) and adds
five evaluation-only scenarios with ten populations each (seeds 101–110):
group-size imbalance, label base-rate shift, 8% label noise, stronger protected-
attribute/proxy correlations, and community-specific merit-feature shift. These
scenarios are not used for training or policy selection. The gate reports results
by scenario as well as over all 100 populations.

At the fixed global 0.5 platform-score cutoff, TalentFit v4's combined synthetic
holdout mean accuracy is **81.29%** (95% population-bootstrap interval
80.73–81.86%, p10 78.20%); mean recall is **96.21%** (95.62–96.72%, p10
90.98%); mean false-positive rate is **28.72%** (27.68–29.68%, p90 33.83%);
mean worst disparate impact is **0.7979** (0.7761–0.8191, p10 0.6497); and
**63%** of populations pass the four-fifths check on all three primary
attributes (bootstrap interval 54–72%). The intervals describe variation across
these generated populations, not uncertainty about real employers or applicants.
The merit-feature shift scenario has high accuracy but 0% four-fifths passes and
p10 worst DI 0.4742, demonstrating why aggregate averages alone are insufficient.

The default population guardrails are explicit: mean accuracy ≥0.78, p10 accuracy
≥0.70, mean recall ≥0.90, p10 recall ≥0.80, mean FPR ≤0.40, p90 FPR ≤0.50,
p10 worst-DI ≥0.55, and four-fifths pass rate ≥0.25. Operators can set these
limits independently through the API, CLI, or gate panel. They are synthetic
demo limits, not recommendations or production-readiness thresholds.

The same study reports global score-cutoff sensitivity at 0.45, 0.475, 0.50,
0.525, and 0.55, applying each threshold uniformly to every candidate and group.
Lower thresholds raise recall and FPR; higher thresholds reduce FPR and recall,
with fairness metrics also moving. `train --calibration-study` separately reports
raw logistic-probability Brier/ECE diagnostics and subgroup uncertainty; those
subgroup results are diagnostics only and never set thresholds. The runtime
platform score is affine and is not itself a calibrated probability. The policy
study also reports a Pareto frontier across worst DI, accuracy, recall, and FPR,
and accepts optional maximum-FPR/minimum-recall constraints before selection.
See the [TalentFit v4 model card](../operations/MODEL-CARD-TALENTFIT-V4.md)
for scenario tables, intervals, calibration results, the exact artifact digest,
known failure modes, intended use, and human-review requirements.

**Proxies.** The original v3 was offered college prestige and career gap. The
label never uses them, so they received near-zero weight (+0.012 and +0.030,
the positive gap weight a chance correlation) and zeroing them changed 23
decisions. TalentFit v4 continues to drop both (the platform's own
proxy-removal mitigation); refitting them on this fixture ties the fairness
score at 85 but changes decisions on a random correlation. They are not restored
because the label contains no legitimate signal for them. On real data, where
proxies can carry signal, this has to be independently measured, not assumed.

**Resilience.** A counterfactual swap can only flip a decision if the model
reads the swapped signal. MeritFirst and TalentFit carry no weight on gender,
community or age, and no penalty for a career gap, so four of their five chaos
experiments pass **by construction**. The `/api/chaos` payload labels them
(`by_construction`, `passes_by_construction`, `resilience_scope`). A 100/100
resilience score shows what a model does not read directly. It is not evidence
of equal outcomes.

Optimising accuracy alone gives no reason to expect a better fairness score.
TalentFit v4 makes that trade-off explicit with one global threshold, a minimum
accuracy guardrail, a separate synthetic holdout, and visible false-positive
rates. The study is not a fairness guarantee: real use would require
representative, legally collected data, domain-led cost assumptions, independent
subgroup and uncertainty analysis, human oversight, and appropriate legal,
privacy, and security review. ChaosHire's synthetic reference must not be used to
make real employment decisions.
