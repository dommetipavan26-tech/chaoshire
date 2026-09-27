# Real-data audit: UCI Adult (Census Income)

Every other ChaosHire number comes from a synthetic 1,000-candidate fixture.
This page runs the **same, unchanged audit engine** (`chaoshire.metrics.audit`)
on a real public dataset to see how the metrics behave on data they were not
written against.

```bash
python -m pip install -r requirements-examples.txt
python -m examples.adult_income_audit                      # print the audit
python -m examples.adult_income_audit --json adult.json --csv adult-decisions.csv
```

The script downloads `adult.data` and `adult.test` from UCI once into
`data/adult/` (git-ignored) and checks them against pinned SHA-256 digests.
If the digests don't match, it prints a warning. Use `--data-dir` to point at a
local copy, or `--no-download` to fail instead of fetching. The code is in
[`examples/adult_income_audit.py`](../../examples/adult_income_audit.py) and is
tested offline by `tests/core/test_adult_example.py`.

## Setup

| | |
|---|---|
| Data | UCI Adult, 1994 US Census extract; rows with missing values dropped |
| Train / test | Official split: **30,162** train rows, **15,060** held-out test rows |
| "Accepted" | Model predicts income > $50K (stand-in for a favourable screening decision) |
| "Qualified" | The true census label (income > $50K), **24.6%** of test rows |
| Audited attributes | `sex`, `race`, `age_band` (Under 40 / 40+, the US ADEA boundary) |
| Model | scikit-learn logistic regression (standard-scaled numerics, one-hot categoricals), seed 1046 |

Three models, plus the label itself as a reference:

| ID | Inputs |
|---|---|
| `naive` | Every column, including sex and race |
| `blind` | Drops sex, race **and** their proxies: `relationship` (encodes Husband/Wife), `marital_status`, `native_country` |
| `blind_no_age` | `blind` without the `age` input, since age band is audited |
| `true_label` | Not a model: the true label audited as if it were one (a perfect predictor) |

## Results (held-out test split)

| Model | Accuracy | Fairness risk score | High earners missed | DI sex | DI race | DI age | Eq-opp gap sex | Eq-opp gap age |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `naive` | **84.7%** | 12 / F | **1,478** | 0.300 | 0.203 | 0.385 | 0.100 | 0.136 |
| `blind` | 81.5% | 15 / F | 2,116 | **0.471** | **0.380** | 0.249 | 0.064 | 0.237 |
| `blind_no_age` | 81.3% | 12 / F | 2,225 | 0.462 | 0.211 | **0.464** | **0.034** | **0.079** |
| `true_label` | 100% | **51 / D** | 0 | 0.366 | 0.402 | 0.455 | 0.000 | 0.000 |

DI = disparate impact (four-fifths rule needs ≥ 0.80). **Every model fails it
on every attribute, and so does the perfect predictor.**

True high-income rate by group (test split):

| Sex | | Race | | Age | |
|---|---:|---|---:|---|---:|
| Male | 31.0% | White | 26.0% | 40+ | 35.3% |
| Female | 11.3% | Asian-Pac-Islander | 29.7% | Under 40 | 16.1% |
| | | Other (n = 122) | 19.7% | | |
| | | Amer-Indian-Eskimo (n = 149) | 12.8% | | |
| | | Black | 11.9% | | |

## What the real data shows

1. **Unequal labels come first.** In the 1994 data, women were about a third
   as likely as men to earn over $50K. A model that predicts the label
   perfectly (51/D) still fails the four-fifths rule on sex, race and age.
   This is the same "label inequality" effect the README describes for
   TalentFit v3, but here it's much larger and comes from real data rather
   than sampling noise. On this dataset, disparate impact measures inequality
   in the world as much as bias in the model.

2. **Removing sex and race isn't enough.** The blind model still selects women
   at under half the male rate (DI 0.471). Occupation, hours worked and
   education carry the gap in indirectly, so proxies remain even after the
   obvious ones are dropped.

3. **Blinding one attribute can hurt another.** Removing sex, race and proxies
   improved DI for sex and race but made age worse (0.385 → 0.249). The model
   leaned harder on the `age` input it still had. Removing age as well fixed
   the age gap (DI 0.464, eq-opp gap 0.079) but pushed race DI back down to
   0.211. Every fairness change should be re-audited on **all** attributes.

4. **Fairness here costs accuracy and recall.** Each blinding step lost
   accuracy and missed more true high earners (1,478 → 2,225). Some of the
   narrower selection-rate gaps simply come from the blind models selecting
   fewer people overall. This is the same trade-off ChaosHire reports for its
   synthetic models, now visible at real scale.

5. **Equal opportunity is the better metric on this data.** Since the label
   itself fails DI, the fairer question is: among people who really earn over
   $50K, does each group get recognised equally? On that metric, the
   `blind_no_age` model is clearly best for sex (0.034) and age (0.079).

## A limitation this audit uncovered

The race equal-opportunity gap (0.25–0.35 for every model) comes mainly from
the **Amer-Indian-Eskimo** group. That group has 149 rows, which clears the
minimum group size of 30, but only about **19 truly high-income people**. Its
true-positive rate is therefore estimated from about 19 people and is very
noisy. ChaosHire's `low_n` flag checks the whole group's size, not the number
of qualified people in the group, so this equal-opportunity comparison isn't
flagged as unreliable. The confidence interval (`tpr_ci`) in the JSON output
does show the width. A sensible future fix is to apply the minimum-size check
to the qualified count when computing equal-opportunity gaps.

## Responsible-use notes

- Adult is an **income** benchmark from 1994, not hiring data. It's used here
  because it's the standard public fairness benchmark with real protected
  attributes.
- `race` and `sex` categories are the census's own coding and are
  not a recommended way to record identity.
- These numbers are screening evidence for discussion, not findings about any
  employer and not a legal assessment.

## Load it in the dashboard

`--csv` writes the `blind` model's decisions in the configurable upload format.
In **Audit your own decisions**, use decision column `decision`, favourable
value `advance`, qualification column `high_income`, qualified value `yes`,
and protected attributes `sex, race, age_band`.
