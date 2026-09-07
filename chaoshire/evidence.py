"""Tamper-evident aggregate evidence bundles."""
import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def evidence_digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload)).hexdigest()


def build_evidence_bundle(
    audit: dict[str, Any],
    chaos: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "chaoshire.evidence.v1",
        "audit": audit,
        "chaos": chaos,
        "agent_review": review,
    }
    return {"payload": payload, "integrity": {"algorithm": "SHA-256", "digest": evidence_digest(payload)}}


def verify_evidence_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    payload = bundle.get("payload")
    integrity = bundle.get("integrity", {})
    if not isinstance(payload, dict):
        return {"valid": False, "reason": "Bundle payload is missing or invalid."}
    expected = evidence_digest(payload)
    supplied = integrity.get("digest")
    return {
        "valid": supplied == expected,
        "algorithm": "SHA-256",
        "expected": expected,
        "supplied": supplied,
        "reason": "Digest matches canonical aggregate evidence." if supplied == expected else "Digest mismatch.",
    }
