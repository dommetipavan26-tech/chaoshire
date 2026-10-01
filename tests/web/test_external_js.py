"""The dashboard's markup and behavior ship separately without weakening CSP."""

import re
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chaoshire.app as app_module
from chaoshire.app import app
from chaoshire.site import html_version, js_version, site_html

WEB_DIR = Path(__file__).resolve().parents[2] / "chaoshire" / "web"
SCRIPT = WEB_DIR / "static" / "chaoshire.js"


def test_markup_has_one_external_deferred_script_and_no_inline_application_code():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.DOTALL)
    assert len(scripts) == 1
    attrs, body = scripts[0]
    assert 'src="/static/chaoshire.js?v=__JS_VERSION__"' in attrs
    assert "defer" in attrs
    assert body.strip() == ""
    assert "const esc=" not in html
    assert "const esc=" in SCRIPT.read_text(encoding="utf-8")
    templates = ("index.html", "privacy.html", "terms.html", "404.html")
    content = b"\0".join((WEB_DIR / name).read_bytes() for name in templates)
    assert html_version() == sha256(content).hexdigest()[:12]


@pytest.mark.parametrize("version", ["matching", "absent", "stale"])
def test_javascript_cache_is_immutable_only_for_its_current_content_hash(version):
    hashed = sha256(SCRIPT.read_bytes()).hexdigest()[:12]
    assert js_version() == hashed
    url = "/static/chaoshire.js"
    if version == "matching":
        url += f"?v={hashed}"
    elif version == "stale":
        url += "?v=old-build"
    response = TestClient(app).get(url)
    assert response.status_code == 200
    assert response.content == SCRIPT.read_bytes()
    assert response.headers["content-type"].startswith("application/javascript")
    expected = "public, max-age=31536000, immutable" if version == "matching" else "no-cache"
    assert response.headers["cache-control"] == expected
    assert response.headers["x-content-type-options"] == "nosniff"


def test_javascript_is_served_independent_of_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    home = client.get("/")
    assert f'src="/static/chaoshire.js?v={js_version()}"' in home.text
    assert "__JS_VERSION__" not in home.text
    assert "__CSP_NONCE__" not in home.text
    assert client.get("/static/chaoshire.js").content == SCRIPT.read_bytes()


@pytest.mark.parametrize("component", ["js_version", "html_version"])
def test_service_worker_precaches_javascript_and_its_cache_tracks_behavior_and_markup(
    component, monkeypatch
):
    client = TestClient(app)
    before = client.get("/service-worker.js").text
    assert f"/static/chaoshire.js?v={js_version()}" in before
    assert "__JS_VERSION__" not in before
    monkeypatch.setattr(app_module, component, lambda: "abcd01234567")
    after = client.get("/service-worker.js").text
    before_cache = re.search(r"const CACHE='([^']+)';", before)
    after_cache = re.search(r"const CACHE='([^']+)';", after)
    assert before_cache and after_cache
    assert before_cache.group(1) != after_cache.group(1)
    assert "abcd01234567" in after_cache.group(1)
    if component == "js_version":
        assert "/static/chaoshire.js?v=abcd01234567" in after
    else:
        assert after_cache.group(1).endswith("-abcd01234567")


def test_site_renderer_escapes_nonce_attributes():
    html = site_html("index.html", '"><script>alert(1)</script>')
    assert 'nonce="&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"' in html
    assert html.count("<script") == 1


def test_browser_requests_do_not_point_at_sandbox_localhost():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "http://localhost" not in script
    assert "127.0.0.1" not in script
