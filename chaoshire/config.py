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
