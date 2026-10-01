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
If the digests do not match, the default run **stops before training**. Download bytes are capped at 8 MiB per file and the cache is replaced atomically only after verification. `--allow-unverified` is an explicit experimental opt-in: mismatches remain marked and must not be quoted as pinned UCI benchmark evidence. Use `--data-dir` to point at a
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

| Model | Accuracy | Fairness risk score | High earners missed | DI sex | DI race | DI age | Eq-opp gap sex | Eq-opp gap race | Eq-opp gap age |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `naive` | **84.7%** | 18 / F | **1,478** | 0.300 | 0.203 | 0.385 | 0.100 | 0.161 | 0.136 |
| `blind` | 81.5% | 15 / F | 2,116 | **0.471** | **0.380** | 0.249 | 0.064 | 0.089 | 0.237 |
| `blind_no_age` | 81.3% | 30 / F | 2,225 | 0.462 | 0.211 | **0.464** | **0.034** | **0.074** | **0.079** |
| `true_label` | 100% | **51 / D** | 0 | 0.366 | 0.402 | 0.455 | 0.000 | 0.000 | 0.000 |

DI = disparate impact (four-fifths rule needs ≥ 0.80). **Every model fails it
on every attribute, and so does the perfect predictor.**

The race equal-opportunity gaps exclude the two race cells that do not hold
enough qualified people to estimate a true-positive rate from
(**Amer-Indian-Eskimo**, 19 qualified, and **Other**, 24 qualified); see
[the qualified-count check](#the-limitation-this-audit-uncovered-and-the-fix).
Before that check the same gaps were 0.345 / 0.248 / 0.342 / 0.000, which is why
`naive` and `blind_no_age` score higher here than in earlier revisions of this
page (12 → 18 and 12 → 30). `blind` still scores 15 because its age gap of 0.237
already earned zero equal-opportunity points.

True high-income rate by group (test split), with the qualified counts the
equal-opportunity gap is actually estimated from:

| Sex | | Race | Qualified | Age | |
|---|---:|---|---:|---|---:|
| Male | 31.0% | White | 3,368 of 12,970 | 40+ | 35.3% |
| Female | 11.3% | Asian-Pac-Islander | 121 of 408 | Under 40 | 16.1% |
| | | Black | 168 of 1,411 | | |
| | | Other | **24** of 122 | | |
| | | Amer-Indian-Eskimo | **19** of 149 | | |

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
   `blind_no_age` model is clearly best on every attribute: sex (0.034), race
   (0.074) and age (0.079). It is the only fitted model under the 0.10 warning
   threshold on all three; `true_label` is 0.000 on all three by construction,
   and `naive` and `blind` each breach it on at least one attribute.

## The limitation this audit uncovered, and the fix

The race equal-opportunity gap used to read 0.25–0.35 for every model, and it
came mainly from the **Amer-Indian-Eskimo** group. That group has 149 rows,
which clears the minimum group size of 30, but only **19 truly high-income
people**: its true-positive rate is estimated from 19 observations, and its
Wilson 95% interval spans 0.15–0.54 on the `naive` model. The `low_n` flag
checked the whole group's size and nothing else, so the comparison was never
flagged as unreliable — the width was visible only in the `tpr_ci` field of the
JSON output. The same was true, less obviously, of **Other** (122 rows, **24**
qualified).

`chaoshire.metrics.attribute_metrics` now applies the minimum-size check to the
**qualified count** as well as to the group size:

- every group reports `qualified_count` and `low_qualified_n` next to `n` and
  `low_n`;
- a group with fewer than `minimum_group_size` qualified people is excluded from
  the equal-opportunity gap, while staying visible in the report and in the
  selection-rate metrics (disparate impact, parity gap, significance test),
  which are estimated from the whole group;
- the exclusion is stated rather than applied silently: `eq_opp_excluded` and
  `eq_opp_note` in the payload, a "Qualified" column plus a reliability notice in
  the HTML report, and a marker next to the true-positive rate in the dashboard;
- if fewer than two groups survive, the gap is reported as `null` instead of
  being computed from one noisy cell, the equal-opportunity component drops out
  of the score (`basis: "selection-rate-only"`, 60 available points), and the
  reason distinguishes "no qualification labels supplied" from "labels supplied
  but too thin to use".

Effect on this dataset:

| Model | Race eq-opp gap before | after | Groups the gap now compares |
|---|---:|---:|---|
| `naive` | 0.345 | **0.161** | Asian-Pac-Islander, Black, White |
| `blind` | 0.248 | **0.089** | Asian-Pac-Islander, Black, White |
| `blind_no_age` | 0.342 | **0.074** | Asian-Pac-Islander, Black, White |
| `true_label` | 0.000 | 0.000 | Asian-Pac-Islander, Black, White |

Sex and age are unchanged: every cell there holds thousands of qualified people.
The excluded rates are still printed — 31.6% for Amer-Indian-Eskimo on `naive`,
flagged — because a rate that cannot carry a comparison is still a fact about
those 19 people.

The same shape exists in ChaosHire's own synthetic fixture: the non-binary group
has 57 candidates, of whom 17 are qualified, so it is now excluded from the
fixture's gender equal-opportunity gap (0.196 → 0.127). Nothing was wrong with
the synthetic data; the check was simply missing there as well. Both cases are
pinned in `tests/core/test_equal_opportunity_reliability.py`.

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
