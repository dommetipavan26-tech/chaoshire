"""Tests for the external CSS migration and CSP style-src hardening."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from chaoshire.app import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "chaoshire" / "web"
INDEX_HTML = (WEB_DIR / "index.html").read_text(encoding="utf-8")
CSS_FILE = WEB_DIR / "static" / "chaoshire.css"
CSS_CONTENT = CSS_FILE.read_text(encoding="utf-8")


def test_no_inline_style_block_in_html():
    """The <style> block was extracted to chaoshire/web/static/chaoshire.css."""
    assert "<style>" not in INDEX_HTML
    assert "</style>" not in INDEX_HTML


def test_html_links_external_stylesheet():
    assert 'href="/static/chaoshire.css"' in INDEX_HTML


def test_external_css_file_exists():
    assert CSS_FILE.exists()


def test_external_css_has_responsive_rules():
    assert "@media(max-width:600px)" in CSS_CONTENT
    assert "prefers-reduced-motion" in CSS_CONTENT


def test_external_css_has_root_variables():
    assert ":root{" in CSS_CONTENT or ":root {" in CSS_CONTENT
    assert "--bg:#0b1220" in CSS_CONTENT


def test_external_css_has_data_style_utility_classes():
    """Utility classes replaced static inline style attributes."""
    assert ".hero-title" in CSS_CONTENT
    assert ".hero-score" in CSS_CONTENT
    assert ".hero-divider" in CSS_CONTENT


def test_no_static_inline_styles_in_html_body():
    """Static HTML body elements use CSS classes, not style attributes."""
    # These were the static inline styles that got migrated
    assert 'style="margin-top:14px"' not in INDEX_HTML
    assert 'style="margin-top:30px"' not in INDEX_HTML
    assert 'style="margin-top:18px"' not in INDEX_HTML


def test_dynamic_styles_use_data_style_attribute():
    """JS template literals use data-style instead of style for CSP compliance."""
    assert 'data-style="' in INDEX_HTML


def test_data_style_applied_via_cssom_helper():
    """The JS has an applyDataStyles function for CSP compliance."""
    assert "function applyDataStyles" in INDEX_HTML
    assert "data-style" in INDEX_HTML


def test_web_assets_are_packaged_and_served_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as client:
        home = client.get("/")
        css = client.get("/static/chaoshire.css")
        icon = client.get("/icons/icon-192.png")
    assert home.status_code == 200
    assert 'href="/static/chaoshire.css"' in home.text
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert css.text == CSS_CONTENT
    assert "Cache-Control" in css.headers
    assert icon.status_code == 200
    assert icon.content == (WEB_DIR / "static" / "icons" / "icon-192.png").read_bytes()


def test_csp_style_src_has_no_unsafe_inline():
    with TestClient(app) as client:
        response = client.get("/")
    csp = response.headers["content-security-policy"]
    style_src = csp.split("style-src")[1].split(";")[0]
    assert "'unsafe-inline'" not in style_src
    assert "'self'" in style_src


def test_service_worker_precaches_css():
    with TestClient(app) as client:
        sw = client.get("/service-worker.js").text
    assert "/static/chaoshire.css" in sw
