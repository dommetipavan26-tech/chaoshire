"""Fix #4 — write access, rate limits, and the bounded appeal queue.

Before this change the public demo was defaceable and exhaustible:

* ``require_write_access`` was a **no-op** unless ``CHAOSHIRE_API_KEY`` happened
  to be set, and ``render.yaml`` marked it ``sync: false`` — so it was never set.
* ``CHAOSHIRE_RATE_LIMIT_PER_MINUTE`` defaulted to ``"0"``, which disabled the
  limiter entirely.
* ``POST /api/upload`` wrote an attacker-chosen 100-character audit name into
  persistent SQLite that every later visitor saw in Audit History.
* ``POST /api/appeals`` appended 5,000-character messages to an unbounded
  in-memory list with no cap and no eviction.

The posture now: a key is generated at deploy time; holding it is what makes an
upload *published*; anonymous writes are allowed but budgeted and never
published; and the appeal queue is a capped FIFO.
"""

import csv
import io
import logging

import pytest
from conftest import TEST_API_KEY, operator_client
from fastapi.testclient import TestClient

import backend
from chaoshire import __version__
from chaoshire.platform import LIMITER
from chaoshire.services import sanitise_audit_name
from chaoshire.state import APPEALS


def _csv(rows: int = 80) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["gender", "decision", "qualified"])
    for index in range(rows):
        writer.writerow(["F" if index % 2 else "M", index % 3 != 0, 1])
    return buffer.getvalue()


def upload(client: TestClient, name: str = "Probe audit") -> dict:
    return client.post("/api/upload", json={"csv": _csv(), "audit_name": name})


# --- fail closed -----------------------------------------------------------


def test_writes_are_refused_when_no_key_is_configured_and_anonymous_is_off(monkeypatch):
    monkeypatch.delenv("CHAOSHIRE_API_KEY", raising=False)
    monkeypatch.setenv("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", "0")
    with TestClient(backend.app) as client:
        response = client.post("/api/appeals", json={"candidate_id": "C-1046", "message": "hi"})
    assert response.status_code == 503
    assert "CHAOSHIRE_API_KEY" in response.json()["detail"]


def test_writes_need_the_key_when_anonymous_is_off_and_a_key_exists(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", "0")
    with TestClient(backend.app) as client:
        refused = client.post("/api/appeals", json={"candidate_id": "C-1046", "message": "hi"})
        assert refused.status_code == 401

        allowed = client.post(
            "/api/appeals",
            json={"candidate_id": "C-1046", "message": "hi"},
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert allowed.status_code == 200


def test_a_wrong_key_is_rejected_rather_than_silently_downgraded(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", "1")
    with TestClient(backend.app) as client:
        response = client.post(
            "/api/appeals",
            json={"candidate_id": "C-1046", "message": "hi"},
            headers={"X-API-Key": "not-the-key"},
        )
    assert response.status_code == 401
    assert "rejected" in response.json()["detail"]


# --- publishing is what the key buys ---------------------------------------


def test_anonymous_upload_is_audited_but_never_published():
    with TestClient(backend.app) as anonymous:
        response = upload(anonymous, name="<script>defaced</script>")
        assert response.status_code == 200
        body = response.json()
        assert body["published"] is False
        assert body["audit_id"] is None
        assert body["audit"]["stats"]["candidates"] == 80
        assert "not published" in body["publishing_note"]

        # Nothing landed in the shared slot or the persistent history.
        assert anonymous.get("/api/audit", params={"dataset": "uploaded"}).status_code == 404
        assert anonymous.get("/api/audits").json()["audits"] == []


def test_authenticated_upload_is_published_to_history_and_the_shared_slot():
    client = operator_client()
    response = upload(client, name="Operator review")
    assert response.status_code == 200
    body = response.json()
    assert body["published"] is True
    assert body["audit_id"]
    assert body["audit_id"].startswith("AUD-")

    shared = client.get("/api/audit", params={"dataset": "uploaded"})
    assert shared.status_code == 200
    assert shared.json()["stats"]["candidates"] == 80

    history = client.get("/api/audits").json()["audits"]
    assert len(history) == 1
    assert history[0]["name"] == "Operator review"


def test_the_defacement_vector_is_closed():
    """An attacker-chosen audit name can no longer reach a shared surface."""
    hostile = '<img src=x onerror="alert(1)"> PWNED'
    with TestClient(backend.app) as anonymous:
        response = upload(anonymous, name=hostile)
        assert response.status_code == 200
        body = response.json()
        assert body["published"] is False
        assert body["audit_id"] is None
        # Returned to the uploader only: nothing reached the shared history.
        assert anonymous.get("/api/audits").json()["audits"] == []
        assert anonymous.get("/api/audit", params={"dataset": "uploaded"}).status_code == 404

    # Even an authenticated operator's name is normalised and capped.
    stored = sanitise_audit_name(hostile + "\x00" + " " * 12 + "y" * 500)
    assert "<img" in stored  # markup is data, and the renderer escapes it
    assert len(stored) <= 60
    assert "\x00" not in stored
    assert "  " not in stored


def test_audit_name_sanitiser_strips_control_characters_and_caps_length():
    assert sanitise_audit_name(None) == "Untitled CSV audit"
    assert sanitise_audit_name("   ") == "Untitled CSV audit"
    # Control characters become spaces and whitespace runs collapse, so a name
    # can never smuggle a newline into a single-line UI row.
    assert sanitise_audit_name("a\x00b\x1f c\n\td") == "a b c d"
    assert sanitise_audit_name("a  b\n\nc") == "a b c"
    assert len(sanitise_audit_name("y" * 5000)) == 60


# --- rate limits -----------------------------------------------------------


def test_write_budget_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE", "3")
    LIMITER.reset()
    with TestClient(backend.app) as client:
        statuses = [
            client.post("/api/appeals", json={"candidate_id": "C-1046", "message": "x"}).status_code
            for _ in range(5)
        ]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3:] == [429, 429]
    LIMITER.reset()


def test_429_carries_a_retry_after_header(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE", "1")
    LIMITER.reset()
    with TestClient(backend.app) as client:
        client.post("/api/appeals", json={"candidate_id": "C-1046", "message": "x"})
        blocked = client.post("/api/appeals", json={"candidate_id": "C-1046", "message": "x"})
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    LIMITER.reset()


def test_global_rate_limit_defaults_are_non_zero():
    from chaoshire import platform

    assert platform.DEFAULT_RATE_LIMIT_PER_MINUTE > 0
    assert platform.DEFAULT_WRITE_RATE_LIMIT_PER_MINUTE > 0


def test_forwarded_for_is_only_trusted_when_declared(monkeypatch):
    from chaoshire.platform import client_key

    class FakeRequest:
        def __init__(self, headers, host):
            self.headers = headers
            self.client = type("C", (), {"host": host})

    request = FakeRequest({"x-forwarded-for": "1.2.3.4, 10.0.0.1"}, "10.0.0.1")
    monkeypatch.delenv("CHAOSHIRE_TRUST_FORWARDED_FOR", raising=False)
    assert client_key(request) == "10.0.0.1"

    monkeypatch.setenv("CHAOSHIRE_TRUST_FORWARDED_FOR", "1")
    # Render documents the left-most entry as the client IP it observed.
    assert client_key(request) == "1.2.3.4"
    assert client_key(FakeRequest({"x-forwarded-for": "9.9.9.9, spoofed"}, "p")) == "9.9.9.9"
    assert client_key(FakeRequest({"x-forwarded-for": "203.0.113.10:54321"}, "p")) == "203.0.113.10"


# --- bounded appeal queue --------------------------------------------------


def test_appeal_queue_is_bounded_and_evicts_oldest_first(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_MAX_APPEALS", "5")
    APPEALS.set_capacity(5)
    client = operator_client()
    for index in range(12):
        response = client.post(
            "/api/appeals", json={"candidate_id": "C-1046", "message": f"appeal {index}"}
        )
        assert response.status_code == 200

    queue = client.get("/api/appeals").json()
    assert queue["capacity"] == 5
    assert queue["bounded"] is True
    assert len(queue["appeals"]) == 5
    assert queue["evicted"] == 7
    assert "evicted" in queue["note"]
    # Newest first, and ids stay unique across evictions.
    assert [appeal["message"] for appeal in queue["appeals"]] == [
        f"appeal {index}" for index in range(11, 6, -1)
    ]
    assert len({appeal["id"] for appeal in queue["appeals"]}) == 5
    APPEALS.set_capacity(200)


def test_appeal_queue_memory_is_bounded_even_with_maximum_messages(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_MAX_APPEALS", "200")
    APPEALS.set_capacity(200)
    client = operator_client()
    longest = "x" * 5000  # AppealRequest.message max_length
    for _ in range(260):
        assert (
            client.post(
                "/api/appeals", json={"candidate_id": "C-1046", "message": longest}
            ).status_code
            == 200
        )
    queue = client.get("/api/appeals").json()
    assert len(queue["appeals"]) == 200
    # 200 x 5,000 characters is ~1 MB, not an unbounded list on a 512 MB instance.
    assert sum(len(appeal["message"]) for appeal in queue["appeals"]) == 200 * 5000


def test_meta_reports_the_write_posture():
    from chaoshire.platform import ANONYMOUS_UPLOADS_PUBLISHED, anonymous_uploads_published

    body = operator_client().get("/api/meta").json()
    posture = body["platform"]
    assert posture["api_key_configured"] is True
    assert posture["anonymous_uploads_published"] is ANONYMOUS_UPLOADS_PUBLISHED
    assert posture["anonymous_uploads_published"] is anonymous_uploads_published()
    assert posture["appeals_capacity"] == 200
    assert posture["rate_limit_per_minute"] == 0  # disabled by conftest for speed
    assert posture["limiter_scope"] == "process-local-memory"
    assert posture["disclosed"] is True
    assert "published" in posture["note"]


@pytest.mark.parametrize("path", ["/api/upload", "/api/appeals", "/api/connectors/audit"])
def test_every_mutating_route_is_gated(path):
    """No mutating route may be registered without the write-access dependency."""
    from chaoshire.app import app as fastapi_app
    from chaoshire.platform import require_write_access

    matched = 0
    for route in fastapi_app.routes:
        if getattr(route, "path", None) == path and "POST" in getattr(route, "methods", set()):
            matched += 1
            assert require_write_access in _dependency_calls(route.dependant), (
                f"{path} accepts writes without require_write_access"
            )
    assert matched == 1, f"expected exactly one POST route at {path}, found {matched}"


def _dependency_calls(dependant) -> list:
    calls = [sub.call for sub in dependant.dependencies]
    for sub in dependant.dependencies:
        calls.extend(_dependency_calls(sub))
    return calls


# --- the write posture is verifiable in production ---------------------------


def test_meta_discloses_the_proxy_and_bucketing_posture(monkeypatch):
    """/api/meta names the variable that decides how rate limits bucket.

    Unset means every visitor shares one per-instance bucket; "1" means the
    trusted proxy's right-most X-Forwarded-For entry identifies each client.
    """
    monkeypatch.delenv("CHAOSHIRE_TRUST_FORWARDED_FOR", raising=False)
    with TestClient(backend.app) as client:
        posture = client.get("/api/meta").json()["platform"]
        assert posture["trusted_proxy_headers"] is False
        assert posture["rate_limit_bucketing"] == "shared-per-instance"
        assert "CHAOSHIRE_TRUST_FORWARDED_FOR" in posture["note"]

    monkeypatch.setenv("CHAOSHIRE_TRUST_FORWARDED_FOR", "1")
    with TestClient(backend.app) as client:
        posture = client.get("/api/meta").json()["platform"]
        assert posture["trusted_proxy_headers"] is True
        assert posture["rate_limit_bucketing"] == "per-client-ip"
        assert "CHAOSHIRE_TRUST_FORWARDED_FOR" in posture["note"]


def test_boot_log_reports_the_posture_without_the_key(monkeypatch, caplog):
    """Entering the app logs the resolved write posture exactly once.

    This is the line an operator greps for in the Render log stream to confirm
    the deployment started with the intended configuration. It carries the
    resolved facts as key=value pairs — the API key itself must never appear
    in it.
    """
    monkeypatch.setenv("CHAOSHIRE_TRUST_FORWARDED_FOR", "1")
    with caplog.at_level(logging.INFO, logger="chaoshire.app"):
        with TestClient(backend.app):
            pass
    lines = [
        record.getMessage()
        for record in caplog.records
        if "resolved write posture" in record.getMessage()
    ]
    assert len(lines) == 1
    assert f"chaoshire {__version__} resolved write posture:" in lines[0]
    # Literal-producing ternaries, not Python bools: keeps CodeQL's
    # clear-text-logging query from treating an env-derived bool as taint.
    assert "api_key_configured=true" in lines[0]
    assert "trusted_proxy_headers=true" in lines[0]
    assert "rate_limit_bucketing=per-client-ip" in lines[0]
    assert "limiter_scope=process-local-memory" in lines[0]
    assert TEST_API_KEY not in lines[0]
    assert "True" not in lines[0]
    assert "False" not in lines[0]


def test_importing_app_does_not_call_basic_config():
    """Embedding hosts must not have their logging rewritten at import time."""
    import inspect

    import chaoshire.app as app_module

    source = inspect.getsource(app_module)
    assert "logging.basicConfig" not in source


def test_spoofed_leftmost_xff_cannot_escape_the_write_budget(monkeypatch):
    """Unique XFF identities still hit the process-wide write backstop."""
    monkeypatch.setenv("CHAOSHIRE_TRUST_FORWARDED_FOR", "1")
    monkeypatch.setenv("CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE", "3")
    LIMITER.reset()
    with TestClient(backend.app) as client:
        statuses = []
        for index in range(4):
            statuses.append(
                client.post(
                    "/api/appeals",
                    json={"candidate_id": "C-1046", "message": "x"},
                    headers={"X-Forwarded-For": f"{index}.1.1.1"},
                ).status_code
            )
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429
    LIMITER.reset()


def test_instance_write_cap_fires_even_when_every_request_has_a_new_ip(monkeypatch):
    """The live 7×200 failure: per-client keys did not collapse, so we cap the process."""
    monkeypatch.setenv("CHAOSHIRE_TRUST_FORWARDED_FOR", "1")
    monkeypatch.setenv("CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE", "6")
    LIMITER.reset()
    with TestClient(backend.app) as client:
        statuses = [
            client.post(
                "/api/appeals",
                json={"candidate_id": "C-1046", "message": "x"},
                headers={"X-Forwarded-For": f"198.51.100.{index}"},
            ).status_code
            for index in range(7)
        ]
    assert statuses[:6] == [200, 200, 200, 200, 200, 200]
    assert statuses[6] == 429
    LIMITER.reset()


def test_meta_redacts_recon_when_disclosure_is_off(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DISCLOSE_WRITE_POSTURE", "0")
    with TestClient(backend.app) as client:
        posture = client.get("/api/meta").json()["platform"]
    assert posture["disclosed"] is False
    assert "api_key_configured" not in posture
    assert "rate_limit_per_minute" not in posture
    assert "trusted_proxy_headers" not in posture
    assert posture["anonymous_uploads_published"] is False
    assert "/api/ops/posture" in posture["note"]


def test_operator_posture_returns_the_full_picture_when_meta_is_redacted(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DISCLOSE_WRITE_POSTURE", "0")
    client = operator_client()
    public = client.get("/api/meta").json()["platform"]
    assert public["disclosed"] is False
    full = client.get("/api/ops/posture")
    assert full.status_code == 200
    body = full.json()
    assert body["api_key_configured"] is True
    assert body["limiter_scope"] == "process-local-memory"
    refused = TestClient(backend.app).get("/api/ops/posture")
    assert refused.status_code == 401


def test_whoami_reports_leftmost_xff_when_trusted(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_TRUST_FORWARDED_FOR", "1")
    client = operator_client()
    body = client.get(
        "/api/ops/whoami",
        headers={"X-Forwarded-For": "203.0.113.99, 1.2.3.4"},
    ).json()
    assert body["client_key"] == "203.0.113.99"
    assert body["source"] == "x-forwarded-for-leftmost"
    assert body["xff_entry_count"] == 2


def test_anonymous_appeals_are_evicted_before_authenticated_ones(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_MAX_APPEALS", "3")
    APPEALS.set_capacity(3)
    operator = operator_client()
    assert (
        operator.post(
            "/api/appeals", json={"candidate_id": "C-1046", "message": "keep-me"}
        ).status_code
        == 200
    )
    anonymous = TestClient(backend.app)
    for index in range(5):
        assert (
            anonymous.post(
                "/api/appeals",
                json={"candidate_id": "C-1046", "message": f"anon {index}"},
            ).status_code
            == 200
        )
    queue = operator.get("/api/appeals").json()
    messages = [appeal["message"] for appeal in queue["appeals"]]
    assert "keep-me" in messages
    assert messages.count("keep-me") == 1
    assert all(
        appeal["protected"] is True for appeal in queue["appeals"] if appeal["message"] == "keep-me"
    )
    APPEALS.set_capacity(200)


def test_anonymous_appeals_have_their_own_budget(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE", "2")
    LIMITER.reset()
    with TestClient(backend.app) as client:
        statuses = [
            client.post("/api/appeals", json={"candidate_id": "C-1046", "message": "x"}).status_code
            for _ in range(3)
        ]
        operator = client.post(
            "/api/appeals",
            json={"candidate_id": "C-1046", "message": "op"},
            headers={"X-API-Key": TEST_API_KEY},
        )
    assert statuses == [200, 200, 429]
    assert operator.status_code == 200
    LIMITER.reset()


def test_blueprint_contract_matches_render_yaml():
    import re
    from pathlib import Path

    from chaoshire.platform import BLUEPRINT_CONTRACT

    text = (Path(__file__).resolve().parent.parent / "render.yaml").read_text(encoding="utf-8")
    for name, expected in BLUEPRINT_CONTRACT.items():
        match = re.search(
            rf"- key:\s*{re.escape(name)}\n\s+value:\s*\"([^\"]+)\"",
            text,
        )
        assert match, f"{name} missing from render.yaml"
        assert match.group(1) == expected, f"{name}: yaml={match.group(1)!r} contract={expected!r}"


def test_hardening_helpers_cover_edge_branches(monkeypatch):
    import logging

    from chaoshire import platform, state

    assert platform._int_env("CHAOSHIRE_RATE_LIMIT_PER_MINUTE", 120) == 0  # conftest
    monkeypatch.setenv("CHAOSHIRE_NOT_AN_INT", "nope")
    assert platform._int_env("CHAOSHIRE_NOT_AN_INT", 7) == 7
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    assert platform.process_worker_count() == 4
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.setenv("UVICORN_WORKERS", "2")
    assert platform.process_worker_count() == 2

    monkeypatch.setattr(platform, "ANONYMOUS_UPLOADS_PUBLISHED", True)
    assert "also published" in platform.write_posture_note()

    isolated = logging.getLogger("chaoshire.ensure-test")
    isolated.handlers.clear()
    isolated.propagate = False
    platform.ensure_package_logging(isolated)
    assert isolated.handlers
    platform.ensure_package_logging(isolated)  # already has a handler

    assert platform.LIMITER.retry_after("never-seen") >= 1
    platform.LIMITER.reset()

    monkeypatch.delenv("CHAOSHIRE_API_KEY", raising=False)
    from fastapi import HTTPException

    try:
        platform.require_operator(x_api_key=None)
        raise AssertionError("expected 503")
    except HTTPException as error:
        assert error.status_code == 503

    class Bare:
        headers = {}
        client = None

    monkeypatch.delenv("CHAOSHIRE_TRUST_FORWARDED_FOR", raising=False)
    assert platform.client_key(Bare()) == "unknown"

    monkeypatch.setenv("CHAOSHIRE_MAX_APPEALS", "not-a-number")
    assert state.appeals_capacity() == state.DEFAULT_APPEALS_CAPACITY
    queue = state.AppealQueue(2)
    assert len(queue) == 0
    queue.append({"message": "a", "protected": True})
    queue.append({"message": "b", "protected": True})
    queue.append({"message": "c", "protected": True})  # evicts oldest protected
    assert [item["message"] for item in queue] == ["b", "c"]
    assert list(reversed(queue))[0]["message"] == "c"
    assert queue.capacity == 2
    queue.set_capacity(1)
    assert len(queue) == 1
    state.reset_appeals()


def test_head_of_the_landing_page_is_200():
    with TestClient(backend.app) as client:
        headed = client.head("/")
        assert headed.status_code == 200
        assert headed.content == b""
        assert client.get("/").status_code == 200
