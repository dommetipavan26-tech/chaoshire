"""Read-path redaction for the public appeal queue.

``POST /api/appeals`` accepts free text typed by anonymous visitors, and
``GET /api/appeals`` is unauthenticated — it feeds the demo's "HR review queue"
that every visitor can read. Serving those records verbatim therefore
republishes whatever anyone typed, including real names, email addresses and
phone numbers, to every later visitor. The queue is a demonstration aid, not a
case-management system, and nothing in it justifies broadcasting personal data.

Redaction runs on the read path only. The in-memory record keeps the original
text (process-local, never persisted — see ``chaoshire.state``), and every GET
response discloses exactly what the rules are. The rules are deliberately
mechanical string matching — no "PII detection" model is claimed or used:

* ``name`` is masked to initials (``Priya Raman`` → ``P. R.``);
* email addresses become ``[email redacted]``;
* bare runs of 7+ digits become ``[number redacted]``;
* phone-like runs (7+ digits formatted with ``+``, spaces, dashes, dots or
  parentheses) become ``[phone redacted]``.

Over-redaction is preferred to under-redaction: a message that survives
unchanged contains no identifier these rules recognise. Novel formats can still
slip through — "use synthetic data only" remains the rule for the public demo.
"""

import re
from typing import Any

__all__ = [
    "REDACTION_RULES",
    "mask_name",
    "redact_appeal",
    "redact_message",
    "redaction_notice",
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
DIGIT_RUN_RE = re.compile(r"\d{7,}")
PHONE_CANDIDATE_RE = re.compile(r"(?<![\w])(?:\+?\d|\(\d)[\d\s().-]*\d(?![\w])")
NAME_PART_RE = re.compile(r"\S+")

EMAIL_PLACEHOLDER = "[email redacted]"
PHONE_PLACEHOLDER = "[phone redacted]"
NUMBER_PLACEHOLDER = "[number redacted]"

#: The rules every ``GET /api/appeals`` response discloses. Order matters:
#: emails first (they can contain digit runs), then bare digit runs, then
#: formatted phone-like runs built from the smaller pieces.
REDACTION_RULES = (
    "name → initials",
    f"email addresses → {EMAIL_PLACEHOLDER}",
    f"bare 7+ digit runs → {NUMBER_PLACEHOLDER}",
    f"phone-like runs (7+ digits with +, spaces, dashes, dots or parentheses) → {PHONE_PLACEHOLDER}",
)


def mask_name(name: str) -> str:
    """Mask a personal name to its initials (``Priya Raman`` → ``P. R.``)."""
    parts = NAME_PART_RE.findall(name)
    if not parts:
        return ""
    return " ".join(f"{part[0].upper()}." for part in parts)


def _redact_phone_candidate(match: re.Match[str]) -> str:
    token = match.group(0)
    digits = sum(character.isdigit() for character in token)
    formatted = any(character in "+ ().-" for character in token)
    return PHONE_PLACEHOLDER if digits >= 7 and formatted else token


def redact_message(message: str) -> str:
    """Replace recognisable identifiers in free text with fixed placeholders."""
    redacted = EMAIL_RE.sub(EMAIL_PLACEHOLDER, message)
    redacted = DIGIT_RUN_RE.sub(NUMBER_PLACEHOLDER, redacted)
    redacted = PHONE_CANDIDATE_RE.sub(_redact_phone_candidate, redacted)
    return redacted


def redact_appeal(record: dict[str, Any]) -> dict[str, Any]:
    """Return a redacted *copy* of an appeal record; the input is untouched."""
    redacted = dict(record)
    redacted["name"] = mask_name(str(record.get("name", "")))
    redacted["message"] = redact_message(str(record.get("message", "")))
    return redacted


def redaction_notice() -> dict[str, Any]:
    """The disclosure every public appeal listing carries alongside its records."""
    return {
        "applied": True,
        "fields": ["name", "message"],
        "rules": list(REDACTION_RULES),
        "note": (
            "GET /api/appeals serves redacted copies only: names are masked to "
            "initials and messages have emails, bare 7+ digit runs and "
            "phone-like runs replaced with fixed placeholders. The originals "
            "stay in process memory and are never persisted or returned by this "
            "endpoint. Redaction is mechanical string matching and can miss "
            "novel identifier formats — the public demo still accepts synthetic "
            "data only."
        ),
    }
