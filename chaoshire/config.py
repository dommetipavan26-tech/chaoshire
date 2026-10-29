"""Shared application configuration and audit thresholds."""

DEMO_SEED = 29
DEMO_SIZE = 1000
DECISION_THRESHOLD = 0.5
MIN_CELL_SIZE = 30

FAIRNESS_THRESHOLDS = {
    "disparate_impact": 0.8,
    "parity_gap": 0.1,
    "eq_opp_gap": 0.1,
}

# Synthetic population release-gate trade-off limits. These are explicit demo
# guardrails, not evidence of production readiness or real-world performance.
GATE_MIN_HOLDOUT_MEAN_ACCURACY = 0.78
GATE_MIN_HOLDOUT_P10_ACCURACY = 0.70
GATE_MIN_HOLDOUT_MEAN_RECALL = 0.90
GATE_MIN_HOLDOUT_P10_RECALL = 0.80
GATE_MAX_HOLDOUT_MEAN_FALSE_POSITIVE_RATE = 0.40
GATE_MAX_HOLDOUT_P90_FALSE_POSITIVE_RATE = 0.50
GATE_MIN_HOLDOUT_P10_WORST_DI = 0.55
GATE_MIN_HOLDOUT_FOUR_FIFTHS_PASS_RATE = 0.25
