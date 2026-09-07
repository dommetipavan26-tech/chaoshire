"""Stable guided demonstration story for reviewers and interviews."""
from typing import Any

from .agent import review_audit
from .chaos import run_chaos_suite
from .metrics import audit
from .models import FAIR, LEGACY, build_decisions
from .quality import compare_models, evaluate_fairness_gate
from .services import candidate_decision, filtered_candidates, mitigate


def guided_demo() -> dict[str, Any]:
    legacy = audit(build_decisions(LEGACY))
    fair = audit(build_decisions(FAIR))
    chaos = run_chaos_suite("legacy", evidence_limit=3)
    review = review_audit(legacy, chaos)
    comparison = compare_models("legacy", "fair")
    gate = evaluate_fairness_gate("legacy", "fair")
    improved = mitigate(["blind", "proxy", "calibrate"])
    return {
        "title": "From hidden hiring bias to a release decision",
        "duration_minutes": 3,
        "synthetic_data": True,
        "steps": [
            {
                "id": 1,
                "title": "Establish the baseline",
                "message": f"LegacyCorp scores {legacy['certificate']['total']}/{legacy['certificate']['grade']} across 1,000 synthetic candidates.",
                "evidence": {"certificate": legacy["certificate"], "stats": legacy["stats"]},
            },
            {
                "id": 2,
                "title": "Break the model safely",
                "message": f"Controlled identity and stress tests produce resilience {chaos['resilience']}/100.",
                "evidence": {"experiment_id": chaos["experiment_id"], "tests": chaos["tests"]},
            },
            {
                "id": 3,
                "title": "Show the human impact",
                "message": "C-1046 is a qualified rejected candidate with an appeal path.",
                "evidence": {"candidate": candidate_decision("C-1046"), "filtered": filtered_candidates("legacy")},
            },
            {
                "id": 4,
                "title": "Ask the review agent",
                "message": review["summary"],
                "evidence": review,
            },
            {
                "id": 5,
                "title": "Mitigate and compare",
                "message": f"Simulated controls improve the certificate to {improved['after']['certificate']['total']}/{improved['after']['certificate']['grade']}; MeritFirst scores {fair['certificate']['total']}/{fair['certificate']['grade']}.",
                "evidence": {"mitigation": improved, "comparison": comparison},
            },
            {
                "id": 6,
                "title": "Make the release decision",
                "message": f"The automated fairness policy returns {gate['status']} for LegacyCorp to MeritFirst.",
                "evidence": gate,
            },
        ],
    }
