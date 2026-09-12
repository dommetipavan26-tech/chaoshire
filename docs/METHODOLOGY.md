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

## Intersectional analysis

ChaosHire creates every pairwise combination of selected protected attributes. For example:

```text
gender × age_band
region × disability_status
```

It then applies the same group metrics, confidence intervals, small-cell rules, and exploratory significance test to the combined groups.

Intersectional results are reported separately and **do not alter the Fairness Risk Score**. This prevents the risk score from changing merely because more attributes were supplied and avoids double-counting overlapping evidence.

## Risk-score stability

The current risk score uses primary, non-intersectional attributes only:

- Disparate impact: 40 points
- Demographic parity: 20 points
- Equal opportunity: 25 points when ground truth exists
- Transparency features: 15 points

The score is a transparent ChaosHire product indicator—not an official certification from a regulator, standards body, or government agency.
