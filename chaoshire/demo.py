"""Stable guided demonstration story for reviewers and interviews.

Every number in the story is derived from the deterministic fixture at request
time rather than hardcoded, and the whole payload is memoised: it is a pure
function of committed constants, so caching it cannot make it stale.
"""

from functools import lru_cache
from typing import Any

from .agent import review_audit
from .chaos import run_chaos_suite
from .metrics import audit, worst_disparate_impact
from .models import FAIR, LEGACY, build_decisions, get_model
from .quality import compare_models, evaluate_fairness_gate
from .services import (
    THRESHOLD_CONTRAST_STATUTE,
    candidate_decision,
    filtered_candidates,
    mitigate,
)
from .training import disparity_diagnostics


@lru_cache(maxsize=1)
def guided_demo() -> dict[str, Any]:
    """Build the walkthrough once and serve it from memory afterwards.

    This endpoint used to run roughly eight full audits and five chaos suites
    per request on a 0.1 vCPU instance. It is deterministic, so one call's worth
    of work is enough for the lifetime of the process.
    """
    legacy = audit(build_decisions(LEGACY))
    fair = audit(build_decisions(FAIR))
    chaos = run_chaos_suite("legacy", evidence_limit=3)
    review = review_audit(legacy, chaos)
    comparison = compare_models("legacy", "fair")
    gate = evaluate_fairness_gate("legacy", "fair")
    improved = mitigate(["blind", "proxy"])
    refused = mitigate([], threshold_contrast_acknowledged=False)
    trained_audit = audit(build_decisions(get_model("trained")))
    trained_chaos = run_chaos_suite("trained", evidence_limit=0)
    trained_worst = worst_disparate_impact(trained_audit)
    trained_diagnostics = disparity_diagnostics()
    ceiling = trained_diagnostics["label_ceiling"]
    return {
        "title": "From hidden hiring bias to a release decision",
        "duration_minutes": 3,
        "synthetic_data": True,
        "steps": [
            {
                "id": 1,
                "title": "Establish the baseline",
                "message": (
                    f"LegacyCorp has a fairness risk score of "
                    f"{legacy['certificate']['total']}/{legacy['certificate']['grade']} "
                    f"across {legacy['stats']['candidates']:,} synthetic candidates."
                ),
                "evidence": {"certificate": legacy["certificate"], "stats": legacy["stats"]},
            },
            {
                "id": 2,
                "title": "Break the model safely",
                "message": (
                    f"Controlled identity and stress tests produce resilience "
                    f"{chaos['resilience']}/100."
                ),
                "evidence": {"experiment_id": chaos["experiment_id"], "tests": chaos["tests"]},
            },
            {
                "id": 3,
                "title": "Show the human impact",
                "message": "C-1046 is a qualified rejected candidate with an appeal path.",
                "evidence": {
                    "candidate": candidate_decision("C-1046"),
                    "filtered": filtered_candidates("legacy"),
                },
            },
            {
                "id": 4,
                "title": "Run the deterministic fairness review",
                "message": review["summary"],
                "evidence": review,
            },
            {
                "id": 5,
                "title": "Mitigate and compare",
                "message": (
                    f"Blind screening plus proxy removal — the two controls an employer "
                    f"may actually apply — improve the fairness risk score to "
                    f"{improved['after']['certificate']['total']}"
                    f"/{improved['after']['certificate']['grade']}; MeritFirst scores "
                    f"{fair['certificate']['total']}/{fair['certificate']['grade']}."
                ),
                "evidence": {"mitigation": improved, "comparison": comparison},
            },
            {
                "id": 6,
                "title": f"The control ChaosHire refuses to offer ({THRESHOLD_CONTRAST_STATUTE})",
                "message": (
                    "Equalising selection rates by setting a different decision cutoff "
                    "per protected group would raise this fixture's score further without "
                    "touching the model. ChaosHire removed it from the one-click mitigation "
                    f"set because {THRESHOLD_CONTRAST_STATUTE} (Civil Rights Act of 1991) "
                    "makes using different cutoff scores by race, color, religion, sex, or "
                    "national origin an unlawful employment practice. It stays available as "
                    "an explicitly acknowledged, research-only contrast — never as a "
                    "remediation, and never merged into the mitigation result."
                ),
                "evidence": {
                    "refusal": refused,
                    "statute": THRESHOLD_CONTRAST_STATUTE,
                    "statute_url": "https://www.law.cornell.edu/uscode/text/42/2000e-2",
                },
            },
            {
                "id": 7,
                "title": "Audit the model we trained ourselves",
                "message": (
                    f"TalentFit v3 — a logistic regression fitted to this fixture's "
                    f"qualified label with protected attributes withheld — is the most "
                    f"accurate model here ({trained_diagnostics['model']['accuracy']:.1%} "
                    f"agreement with the label) and has resilience "
                    f"{trained_chaos['resilience']}/100, yet scores "
                    f"{trained_audit['certificate']['total']}"
                    f"/{trained_audit['certificate']['grade']}: its worst disparate impact is "
                    f"{trained_worst['disparate_impact']} on {trained_worst['attribute']}. "
                    f"Training optimises agreement with the label, not fairness, and the "
                    f"label itself is uneven across groups — accepting exactly the "
                    f"qualified candidates scores {ceiling['total']}/{ceiling['grade']}. "
                    f"The resilience is by construction: a model with no protected inputs "
                    f"cannot flip on a swap, so it is not evidence of equal outcomes."
                ),
                "evidence": {
                    "certificate": trained_audit["certificate"],
                    "attributes": trained_audit["attributes"],
                    "chaos_resilience": trained_chaos["resilience"],
                    "resilience_scope": trained_chaos["resilience_scope"],
                    "diagnostics": trained_diagnostics,
                },
            },
            {
                "id": 8,
                "title": "Make the release decision",
                "message": (
                    f"The automated fairness policy returns {gate['status']} for LegacyCorp "
                    f"to MeritFirst."
                ),
                "evidence": gate,
            },
        ],
    }
