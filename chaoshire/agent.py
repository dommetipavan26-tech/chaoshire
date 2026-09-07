"""Deterministic, evidence-grounded fairness review agent.

The agent intentionally uses transparent rules rather than an external language model.
Every conclusion links to a metric in the supplied aggregate audit or Chaos run.
"""
import hashlib
import json
from typing import Any


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "REV-" + hashlib.sha256(encoded.encode()).hexdigest()[:12].upper()


def review_audit(audit: dict[str, Any], chaos: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a deterministic risk review and human-action plan."""
    findings: list[dict[str, Any]] = []
    certificate = audit["certificate"]
    if certificate["total"] < 75:
        findings.append(
            {
                "id": "certificate-floor",
                "severity": "HIGH",
                "title": "Fairness certificate is below the release floor",
                "metric": "certificate.total",
                "actual": certificate["total"],
                "threshold": 75,
                "evidence_path": "/certificate/total",
                "explanation": "The combined group-fairness assessment requires remediation before release.",
            }
        )

    intersections = audit.get("intersections", [])
    attributes = list(audit.get("attributes", [])) + list(intersections)
    for attribute in attributes:
        di = attribute.get("disparate_impact")
        if di is not None and di < 0.8:
            intersection = attribute in intersections
            severity = "HIGH" if intersection and di < 0.5 else "MEDIUM" if intersection else "CRITICAL" if di < 0.5 else "HIGH"
            findings.append(
                {
                    "id": f"di-{attribute['attribute']}",
                    "severity": severity,
                    "title": f"Low disparate impact for {attribute['attribute']}",
                    "metric": "disparate_impact",
                    "actual": di,
                    "threshold": 0.8,
                    "evidence_path": (
                        "/intersections" if intersection else "/attributes"
                    ) + f"/{attribute['attribute']}/disparate_impact",
                    "explanation": "The lowest reliable selection rate is below four-fifths of the highest rate.",
                }
            )

    if chaos:
        for test in chaos["tests"]:
            if test["verdict"] in {"WARN", "FAIL"}:
                findings.append(
                    {
                        "id": f"chaos-{test['id']}",
                        "severity": "HIGH" if test["verdict"] == "FAIL" else "MEDIUM",
                        "title": f"{test['name']} returned {test['verdict']}",
                        "metric": test["metric"],
                        "actual": test["rate"],
                        "threshold": test["threshold"],
                        "evidence_path": f"/chaos/tests/{test['id']}",
                        "explanation": test["detail"],
                    }
                )

    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda item: (rank[item["severity"]], item["id"]))
    critical = sum(item["severity"] == "CRITICAL" for item in findings)
    high = sum(item["severity"] == "HIGH" for item in findings)
    disposition = "BLOCK_AND_REVIEW" if critical or high else "REVIEW" if findings else "MONITOR"

    actions = []
    if any(item["id"].startswith("chaos-") for item in findings):
        actions.append("Inspect candidate-level before/after evidence for every failed Chaos experiment.")
    if any(item["metric"] == "disparate_impact" for item in findings):
        actions.append("Review features, proxies, data coverage, and selection thresholds for affected groups.")
    if certificate["total"] < 75:
        actions.append("Run mitigation simulations and require the release gate to pass before promotion.")
    actions.append("Have a qualified human reviewer validate context, labels, and legal relevance.")

    basis = {
        "certificate": certificate,
        "findings": findings,
        "experiment_id": chaos.get("experiment_id") if chaos else None,
    }
    return {
        "review_id": _fingerprint(basis),
        "agent": {
            "name": "ChaosHire Fairness Review Agent",
            "mode": "deterministic_rules",
            "external_ai": False,
            "evidence_grounded": True,
        },
        "disposition": disposition,
        "risk_summary": {"critical": critical, "high": high, "total": len(findings)},
        "summary": (
            f"{len(findings)} evidence-linked fairness finding(s) identified; "
            f"recommended disposition: {disposition}."
        ),
        "findings": findings,
        "recommended_actions": actions,
        "limitations": [
            "This review is decision support, not legal advice or proof of discrimination.",
            "Statistical and counterfactual evidence requires human validation and domain context.",
        ],
    }
