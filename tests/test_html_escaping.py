"""Fix #1 — HTML escaping and the nonce-based Content-Security-Policy.

The dashboard builds HTML by string concatenation, and ``esc()`` used to escape
only ``& < >``. It is interpolated into **attribute** contexts — notably
``title="${esc(g.group)}"`` on the intersections card, where ``g.group`` is
``first + " × " + second`` built from uploaded CSV cell values. A value
containing ``"`` broke straight out of the attribute, and the shipped CSP was
``script-src 'self' 'unsafe-inline'``, so there was nothing behind it.

These tests lock both layers:

1. ``esc()`` covers the attribute quotes (and the backtick, which terminates the
   template literals the page is built from), and every interpolation inside a
   breakout-capable attribute goes through ``esc()``/``encodeURIComponent()``.
2. The CSP forbids ``'unsafe-inline'`` for scripts and carries a fresh per-request
   nonce that the served document's single ``<script>`` tag presents.
3. No inline event handlers survive in the page (they would be blocked anyway,
   and their presence would mean the nonce fix was only half-applied).
"""

import csv
import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaoshire.app import app
from chaoshire.services import upload_decisions

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")

NONCE_RE = re.compile(r"script-src 'self' 'nonce-([^']+)'")
ATTR_INTERPOLATION = re.compile(r'([a-zA-Z-]+)\s*=\s*"([^"]*\$\{[^"]*)"')

#: Attributes where an unescaped value can break out of the attribute and inject
#: markup. Every ``${...}`` inside one of these must start with ``esc(`` or
#: ``encodeURIComponent(``.
BREAKOUT_ATTRIBUTES = {
    "title",
    "href",
    "src",
    "value",
    "alt",
    "placeholder",
    "id",
    "for",
    "name",
}

#: ``class``/``style``/``aria-*`` interpolations are reviewed here rather than
#: escaped, because they must stay valid CSS/class tokens. Every one of them
#: resolves to a page-defined constant, a reviewed constant-returning helper
#: (``gradeColor``, ``dcol``, ``severity``), or numeric arithmetic — none can
#: produce a quote or an angle bracket. Adding an entry means reviewing it.
REVIEWED_PRESENTATIONAL_INTERPOLATIONS = {
    "aria-current": {"i===0?'page':'false'"},
    "aria-pressed": {"m.id===MODEL"},
    "class": {
        "String(a.priority).startsWith('HIGH')?'warn':'info'",
        "String(r.priority).startsWith('HIGH')?'warn':'info'",
        "a.certificate.grade==='A'||a.certificate.grade==='B'?'ok':"
        "a.certificate.grade==='F'?'bad':'warn'",
        "at.statistical_test.significant_at_0_05?'bad':'ok'",
        "bias?'badbar':''",
        "c.grade==='A'||c.grade==='B'?'ok':c.grade==='F'?'bad':'warn'",
        "c.passed?'ok':'bad'",
        "fullBasis?'ok':'warn'",
        "i===0?'on':''",
        "m.id===MODEL?'on':''",
        "ok?'ok':'bad'",
        "r.disposition==='MONITOR'?'ok':'bad'",
        "r.passed?'ok':'bad'",
        "r.published?'ok':'warn'",
        "r.status==='Accepted'?'ok':'bad'",
        "severity(f.severity)",
        "v==='PASS'?'ok':v==='WARN'?'warn':'bad'",
        "x.bias_related?'bad':'info'",
    },
    # ``data-style`` replaced inline ``style`` so the CSP can drop
    # ``style-src 'unsafe-inline'``. Values are applied via CSSOM after
    # innerHTML, not parsed as HTML attribute markup, so the same
    # presentational-constant rule applies.
    "data-style": {
        "assessable?c.total*3.6:0",
        "at.statistical_test.significant_at_0_05?'var(--rose)':'var(--green)'",
        "col",
        "dcol(r.delta.certificate)",
        "dcol(r.delta.chaos_resilience)",
        "dcol(r.delta.worst_disparate_impact)",
        "g.selection_rate*100",
        "g.share*100",
        "gradeColor(a.grade)",
        "gradeColor(b.grade)",
        "r.resilience",
        "r.score*100",
        "rcol",
        "t.count/mx*100",
        "x.chaos_resilience",
        "x.impact<0?'var(--rose)':'var(--green)'",
        "x.worst_disparate_impact*100",
    },
    "style": set(),
}


def _interpolations() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for match in ATTR_INTERPOLATION.finditer(INDEX_HTML):
        attribute, value = match.group(1), match.group(2)
        for expression in re.findall(r"\$\{([^}]*)\}", value):
            found.setdefault(attribute, set()).add(expression.strip())
    return found


def test_esc_covers_attribute_quotes_and_the_template_backtick():
    definition = re.search(r"const esc=s=>String\(s\?\?''\)\.replace\((.*?);\n", INDEX_HTML)
    assert definition, "esc() definition not found or changed shape"
    body = definition.group(1)
    for character in ("&", "<", ">", '"', "'", "`"):
        assert re.search(re.escape(character), body), f"esc() no longer handles {character!r}"
    for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;", "&#96;"):
        assert entity in body, f"esc() no longer emits {entity}"


def test_breakout_capable_attributes_always_escape():
    offenders = []
    for attribute, expressions in _interpolations().items():
        if attribute not in BREAKOUT_ATTRIBUTES and not attribute.startswith("data-"):
            continue
        # data-style values are applied via CSSOM after innerHTML, not parsed
        # as HTML attribute markup, so they are reviewed as presentational
        # (same contract as inline style=), not breakout-capable.
        if attribute in REVIEWED_PRESENTATIONAL_INTERPOLATIONS:
            continue
        for expression in expressions:
            if not expression.startswith(("esc(", "encodeURIComponent(")):
                offenders.append(f'{attribute}="${{{expression}}}"')
    assert not offenders, "unescaped interpolation in a breakout-capable attribute: " + ", ".join(
        offenders
    )


def test_presentational_interpolations_are_reviewed():
    for attribute, expressions in _interpolations().items():
        if attribute in {"class", "style", "data-style"} or attribute.startswith("aria-"):
            reviewed = REVIEWED_PRESENTATIONAL_INTERPOLATIONS.get(attribute, set())
            unreviewed = expressions - reviewed
            assert not unreviewed, (
                f"{attribute}= interpolation(s) not in the reviewed allowlist: "
                f"{sorted(unreviewed)}. They must be constants, numeric arithmetic, or "
                "wrapped in esc()."
            )


def test_no_inline_event_handlers_remain():
    handlers = re.findall(r"\son[a-z]+\s*=\s*[\"']", INDEX_HTML)
    assert not handlers, f"inline event handlers are blocked by the nonce CSP: {handlers}"
    assert "onclick" not in INDEX_HTML


def test_page_has_exactly_one_script_tag():
    assert INDEX_HTML.count("<script") == 1
    assert INDEX_HTML.count("</script>") == 1


def test_csp_is_nonce_based_and_fresh_per_request():
    with TestClient(app) as client:
        first = client.get("/")
        second = client.get("/")

    for response in (first, second):
        csp = response.headers["content-security-policy"]
        script_src = csp.split("script-src")[1].split(";")[0]
        assert "'unsafe-inline'" not in script_src
        # The external stylesheet (chaoshire/static/chaoshire.css) lets the
        # CSP drop style-src 'unsafe-inline'; dynamic values are applied via
        # CSSOM after innerHTML, which is not restricted by style-src.
        style_src = csp.split("style-src")[1].split(";")[0]
        assert "'unsafe-inline'" not in style_src
        assert "'unsafe-eval'" not in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp

    first_nonce = NONCE_RE.search(first.headers["content-security-policy"])
    second_nonce = NONCE_RE.search(second.headers["content-security-policy"])
    assert first_nonce and second_nonce
    assert first_nonce.group(1) != second_nonce.group(1), "nonce was reused across requests"
    assert f'<script nonce="{first_nonce.group(1)}">' in first.text
    assert "<script>" not in first.text


def test_csp_applies_to_every_response_including_the_html_report():
    with TestClient(app) as client:
        for path in ("/", "/api/health", "/api/meta", "/api/report.html?model=legacy"):
            response = client.get(path)
            assert "content-security-policy" in response.headers, path
            assert (
                "'unsafe-inline'"
                not in response.headers["content-security-policy"]
                .split("script-src")[1]
                .split(";")[0]
            )


# Does not start with a quote: a leading '"' would be consumed by CSV quoting
# rules before pandas ever saw it, which would test the parser, not the renderer.
PAYLOAD = 'x"><img src=x onerror="window.__xss=1"><b>pwned</b>'


@pytest.fixture()
def hostile_upload():
    """A decision CSV whose protected-attribute value is an attribute breakout.

    Written through :mod:`csv` so the payload arrives at the parser exactly as
    typed: the point of the test is what the *renderer* does with it, not what a
    hand-built quoting bug would do.
    """
    rows = [PAYLOAD] * 40 + ["M"] * 40
    decisions = ["1"] * 20 + ["0"] * 20 + ["1"] * 20 + ["0"] * 20
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["gender", "ethnicity", "decision", "qualified"])
    for gender, decision in zip(rows, decisions, strict=True):
        writer.writerow([gender, "G1", decision, 1])
    return upload_decisions(csv_text=buffer.getvalue(), audit_name="XSS probe", publish=False)


def test_hostile_group_value_survives_as_data_not_markup(hostile_upload):
    """The API must not mangle the value; escaping is the renderer's job."""
    assert hostile_upload["ok"] is True
    groups = {
        group["group"]
        for attribute in hostile_upload["audit"]["attributes"]
        for group in attribute["groups"]
    }
    assert PAYLOAD in groups


def test_server_rendered_report_escapes_the_hostile_value(hostile_upload):
    from chaoshire.reporting import render_html_report

    html = render_html_report(hostile_upload["audit"])
    assert "<b>pwned</b>" not in html
    assert "<img src=x" not in html
    assert "&lt;b&gt;pwned&lt;/b&gt;" in html
    # html.escape() defaults to quote=True, so the value is also inert inside an
    # attribute if the report template ever gains one.
    assert "&quot;" in html


def test_pdf_report_stays_wellformed_with_a_hostile_value(hostile_upload):
    """A PDF has no markup context, but the payload must not corrupt the file.

    ``_pdf_escape`` neutralises the PDF string delimiters (``\\``, ``(``, ``)``)
    so an uploaded value cannot terminate the content stream early.
    """
    from chaoshire.pdf_reporting import render_pdf_report

    pdf = render_pdf_report(hostile_upload["audit"])
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.endswith(b"%%EOF\n")
    assert pdf.count(b"\nstream\n") == pdf.count(b"endstream") == 1
    # The xref table must still point at a real offset inside the file.
    startxref = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n", 1)[0])
    assert 0 < startxref < len(pdf)
    assert pdf[startxref : startxref + 4] == b"xref"
