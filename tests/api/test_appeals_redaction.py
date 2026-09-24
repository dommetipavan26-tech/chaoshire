"""`GET /api/appeals` serves redacted copies, never the raw queue.

The appeal queue is written by anonymous visitors and read by all of them — the
demo's "HR review queue" is an unauthenticated `GET`. Serving records verbatim
republished whatever anyone typed (names, emails, phone numbers) to every later
visitor. Since v0.23.4 the read path redacts and discloses the rules; the
in-memory record keeps the original text and is never persisted.

These tests pin the redaction rules themselves (unit level) and the behaviour of
the endpoint that applies them (API level).
"""

import re

from conftest import operator_client

from chaoshire.redaction import (
    mask_name,
    redact_appeal,
    redact_message,
    redaction_notice,
)

client = operator_client()

INITIALS_RE = re.compile(r"^([A-Z]\. )*[A-Z]\.$")


def test_mask_name_reduces_a_personal_name_to_initials():
    assert mask_name("Priya Raman") == "P. R."
    assert mask_name("Chen") == "C."
    assert mask_name("Mary Jane Watson") == "M. J. W."
    assert mask_name("  ") == ""
    assert "priya" not in mask_name("Priya Raman").lower()


def test_redact_message_removes_emails_phone_numbers_and_digit_runs():
    message = (
        "I am Jane Roe, reachable at jane.roe+hire@example.com or "
        "+1 (415) 555-0132. My national id is 123-45-6789 and my case is 987654321."
    )
    redacted = redact_message(message)
    assert "jane.roe" not in redacted
    assert "@example.com" not in redacted
    assert "555-0132" not in redacted
    assert "123-45-6789" not in redacted
    assert "987654321" not in redacted
    assert "[email redacted]" in redacted
    assert "[phone redacted]" in redacted
    assert "[number redacted]" in redacted
    # Ordinary language survives untouched.
    assert "I am Jane Roe, reachable at" in redacted


def test_redact_message_leaves_identifier_free_text_unchanged():
    for message in (
        "Please review my application.",
        "appeal 3",
        "x" * 5000,
        "Score 0.4043 against a 0.5 threshold with 50 applicants.",
    ):
        assert redact_message(message) == message


def test_redact_appeal_returns_a_copy_and_never_mutates_the_record():
    record = {"name": "Priya Raman", "message": "mail me at priya@example.org", "id": 1}
    redacted = redact_appeal(record)
    assert redacted is not record
    assert record["name"] == "Priya Raman"
    assert record["message"] == "mail me at priya@example.org"
    assert redacted["name"] == "P. R."
    assert redacted["message"] == "mail me at [email redacted]"
    assert redacted["id"] == 1


def test_the_redaction_rules_are_disclosed_not_hidden():
    notice = redaction_notice()
    assert notice["applied"] is True
    assert notice["fields"] == ["name", "message"]
    assert notice["rules"]
    assert "never persisted" in notice["note"]
    assert "synthetic data only" in notice["note"]


def test_public_appeal_listing_redacts_names_and_messages():
    payload = {
        "candidate_id": "C-1046",
        "message": (
            "Please reconsider. Call Priya at priya.sharma@example.com, "
            "work phone 415-555-0132, badge 51234567."
        ),
    }
    assert client.post("/api/appeals", json=payload).status_code == 200

    body = client.get("/api/appeals").json()
    assert body["redaction"]["applied"] is True
    record = body["appeals"][0]
    assert INITIALS_RE.fullmatch(record["name"]), record["name"]
    assert "priya.sharma@example.com" not in record["message"]
    assert "415-555-0132" not in record["message"]
    assert "51234567" not in record["message"]
    assert "[email redacted]" in record["message"]
    assert "[phone redacted]" in record["message"]
    assert "[number redacted]" in record["message"]
    # The non-identifying triage context a reviewer still needs is kept.
    assert record["candidate_id"] == "C-1046"
    assert record["priority"] == "HIGH — qualified candidate rejected"
    assert record["status"] == "PENDING"


def test_identifier_free_appeals_round_trip_unchanged_through_the_listing():
    assert (
        client.post(
            "/api/appeals", json={"candidate_id": "C-1046", "message": "appeal 3"}
        ).status_code
        == 200
    )
    body = client.get("/api/appeals").json()
    assert body["appeals"][0]["message"] == "appeal 3"
    # Names in the demo fixture are synthetic, but the read path masks them
    # regardless — defence in depth for any deployment that files real names.
    assert INITIALS_RE.fullmatch(body["appeals"][0]["name"])


def test_candidate_lookup_still_shows_the_applicant_their_own_record():
    # The candidate-facing lookup is the applicant's own record; it is not the
    # public queue and is deliberately not redacted the same way.
    assert (
        client.post("/api/appeals", json={"candidate_id": "C-1046", "message": "mine"}).status_code
        == 200
    )
    candidate = client.get("/api/candidate/C-1046").json()
    listed = client.get("/api/appeals").json()["appeals"][0]
    assert candidate["name"] != listed["name"]
