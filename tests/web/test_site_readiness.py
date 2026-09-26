"""Public site/SEO, consented analytics, security and anti-spam contracts."""

from __future__ import annotations

import re
import struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

from conftest import TEST_API_KEY
from fastapi.testclient import TestClient

from chaoshire.app import app
from chaoshire.site import DEFAULT_PUBLIC_ORIGIN
from chaoshire.state import APPEALS


class _LocalLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: set[str] = set()
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if attr.get("id"):
            self.ids.add(str(attr["id"]))
        link = attr.get("href") if tag in {"a", "link"} else attr.get("src")
        if link:
            self.links.add(link)


def test_site_pages_have_distinct_titles_descriptions_and_legal_links() -> None:
    with TestClient(app) as client:
        for route, title in (
            ("/", "ChaosHire | Stress-test hiring AI fairly"),
            ("/privacy", "Privacy Policy | ChaosHire"),
            ("/terms", "Terms &amp; Conditions | ChaosHire"),
        ):
            response = client.get(route)
            assert response.status_code == 200
            assert client.head(route).status_code == 200
            assert f"<title>{title}</title>" in response.text
            assert '<meta name="description"' in response.text
            assert (
                f'href="{DEFAULT_PUBLIC_ORIGIN}{route if route != "/" else "/"}"' in response.text
            )
            assert "__PUBLIC_ORIGIN__" not in response.text
            assert 'href="/privacy"' in response.text
            assert 'href="/terms"' in response.text
        home = client.get("/").text
        assert "while the resume stays still." in home
        assert "résumé" not in home
        assert 'id="home-tab"' not in home.split("</header>")[0]
        assert 'id="home-tab" data-t="welcome"' in home
        assert "anonymous uploads" in client.get("/privacy").text.lower()
        assert "do not use this public service" in client.get("/terms").text.lower()
        compressed = client.get("/", headers={"Accept-Encoding": "gzip"})
        assert compressed.headers["content-encoding"] == "gzip"
        assert int(compressed.headers["content-length"]) < len(compressed.content)


def test_social_card_metadata_and_packaged_images() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
        assert f'content="{DEFAULT_PUBLIC_ORIGIN}/social-preview.png"' in html
        assert 'property="og:image:alt"' in html
        assert 'name="twitter:card" content="summary_large_image"' in html
        preview = client.get("/social-preview.png")
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/png"
        assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack_from(">II", preview.content, 16) == (1200, 630)
        favicon = client.get("/favicon.ico")
        assert favicon.status_code == 200
        assert favicon.content[:4] == b"\x00\x00\x01\x00"
        assert client.get("/icons/favicon-32.png").status_code == 200
        assert 'href="/icons/favicon-32.png"' in html


def test_design_token_text_contrast_meets_wcag_aa() -> None:
    css = (Path(__file__).resolve().parents[2] / "chaoshire/web/static/chaoshire.css").read_text(
        encoding="utf-8"
    )
    colors = dict(re.findall(r"(--[a-z0-9]+):(#[a-fA-F0-9]{6})", css))

    def luminance(color: str) -> float:
        values = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in values
        ]
        return sum(
            channel * weight
            for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)
        )

    def ratio(first: str, second: str) -> float:
        bright, dark = sorted((luminance(first), luminance(second)), reverse=True)
        return (bright + 0.05) / (dark + 0.05)

    for foreground in ("--txt", "--dim", "--blue", "--rose", "--amber"):
        for background in ("--bg", "--card", "--card2"):
            assert ratio(colors[foreground], colors[background]) >= 4.5, (foreground, background)
    primary_text = re.search(r"\.btn\{[^}]*color:(#[a-fA-F0-9]{6})", css)
    assert primary_text is not None
    assert ratio(primary_text.group(1), colors["--blue"]) >= 4.5


def test_robots_and_sitemap_use_canonical_https_not_untrusted_host(monkeypatch) -> None:
    with TestClient(app) as client:
        response = client.get("/robots.txt", headers={"Host": "attacker.example"})
        assert "Disallow: /api/" in response.text
        assert f"Sitemap: {DEFAULT_PUBLIC_ORIGIN}/sitemap.xml" in response.text
        sitemap = client.get("/sitemap.xml", headers={"Host": "attacker.example"})
        assert sitemap.headers["content-type"].startswith("application/xml")
        tree = ElementTree.fromstring(sitemap.text)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = {node.text for node in tree.findall("s:url/s:loc", ns)}
        assert urls == {f"{DEFAULT_PUBLIC_ORIGIN}{p}" for p in ("/", "/privacy", "/terms")}

        monkeypatch.setenv("CHAOSHIRE_PUBLIC_ORIGIN", "http://attacker.example/evil")
        assert DEFAULT_PUBLIC_ORIGIN in client.get("/sitemap.xml").text
        monkeypatch.setenv("CHAOSHIRE_PUBLIC_ORIGIN", "https://demo.example")
        assert "https://demo.example/privacy" in client.get("/sitemap.xml").text
        assert 'href="https://demo.example/terms"' in client.get("/terms").text


def test_browser_404_is_useful_but_unknown_api_stays_json() -> None:
    with TestClient(app) as client:
        missing = client.get("/a-missing-page", headers={"Accept": "text/html"})
        assert missing.status_code == 404
        assert missing.headers["content-type"].startswith("text/html")
        assert missing.headers["x-robots-tag"] == "noindex"
        assert "That page is not here" in missing.text
        assert 'href="/"' in missing.text
        api = client.get("/api/unknown", headers={"Accept": "text/html"})
        assert api.status_code == 404
        assert api.json() == {"detail": "Not Found"}


def test_internal_static_links_and_anchor_targets_resolve() -> None:
    with TestClient(app) as client:
        for route in ("/", "/privacy", "/terms", "/missing-page"):
            html = client.get(route, headers={"Accept": "text/html"}).text
            parser = _LocalLinks()
            parser.feed(html)
            for href in parser.links:
                if href.startswith("#"):
                    assert href[1:] in parser.ids
                elif href.startswith("/"):
                    target = urlsplit(href)
                    response = client.get(target.path, params=target.query or None)
                    assert response.status_code == 200, (route, href, response.status_code)

    # The documentation was reorganized; don't reintroduce dead relative links
    # or a README image that exists only on a developer's machine.
    root = Path(__file__).resolve().parents[2]
    for document in (root / "README.md", root / "CONTRIBUTING.md", *root.glob("docs/**/*.md")):
        for target in re.findall(r"\]\(([^)\n]+)\)", document.read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "#", "mailto:")):
                continue
            relative = target.split("#", maxsplit=1)[0]
            if relative:
                assert (document.parent / relative).exists(), (document, target)


def test_operator_key_never_appears_in_browser_assets_or_public_meta(monkeypatch) -> None:
    secret = "server-only-canary-do-not-publish"
    monkeypatch.setenv("CHAOSHIRE_API_KEY", secret)
    with TestClient(app) as client:
        for path in ("/", "/privacy", "/terms", "/static/chaoshire.css", "/api/meta"):
            assert secret not in client.get(path).text
        assert client.get("/api/meta").json()["platform"]["api_key_configured"] is True


def test_https_redirect_uses_canonical_origin_and_preserves_health_checks(monkeypatch) -> None:
    monkeypatch.setenv("CHAOSHIRE_FORCE_HTTPS", "1")
    monkeypatch.setenv("CHAOSHIRE_TRUST_FORWARDED_PROTO", "0")
    with TestClient(app, follow_redirects=False, base_url="http://testserver") as client:
        redirected = client.get("/privacy?section=analytics", headers={"Host": "evil.example"})
        assert redirected.status_code == 308
        assert (
            redirected.headers["location"] == f"{DEFAULT_PUBLIC_ORIGIN}/privacy?section=analytics"
        )
        assert client.get("/api/ready").status_code == 200
        spoofed = client.get("/terms", headers={"X-Forwarded-Proto": "https"})
        assert spoofed.status_code == 308
        monkeypatch.setenv("CHAOSHIRE_TRUST_FORWARDED_PROTO", "1")
        trusted = client.get("/terms", headers={"X-Forwarded-Proto": "https"})
        assert trusted.status_code == 200
        assert trusted.headers["strict-transport-security"] == "max-age=31536000"
        assert "strict-transport-security" not in redirected.headers


def test_analytics_are_optional_aggregate_and_operator_only() -> None:
    with TestClient(app) as client:
        assert client.get("/api/ops/analytics").status_code == 401
        zero = client.get("/api/ops/analytics", headers={"X-API-Key": TEST_API_KEY}).json()
        assert zero["total_views"] == 0
        response = client.post("/api/analytics/view", json={"page": "welcome"})
        assert response.status_code == 204
        assert response.headers["cache-control"] == "no-store"
        assert "set-cookie" not in response.headers
        invalid = client.post("/api/analytics/view", json={"page": "?email=someone@example.com"})
        assert invalid.status_code == 422
        result = client.get("/api/ops/analytics", headers={"X-API-Key": TEST_API_KEY}).json()
        assert result["retention_days"] == 30
        assert result["total_views"] == 1
        assert sum(day.get("welcome", 0) for day in result["views"].values()) == 1
        assert not re.search(r"(ip|user.agent|referrer|email)", str(result), re.I)


def test_analytics_endpoint_is_throttled_separately_from_demo_writes() -> None:
    with TestClient(app) as client:
        codes = [
            client.post("/api/analytics/view", json={"page": "demo"}).status_code for _ in range(31)
        ]
        assert codes[:30] == [204] * 30
        assert codes[30] == 429
        operator = client.get("/api/ops/analytics", headers={"X-API-Key": TEST_API_KEY}).json()
        assert operator["total_views"] == 30


def test_appeal_honeypot_and_blank_message_reject_spam() -> None:
    with TestClient(app) as client:
        spam = client.post(
            "/api/appeals",
            json={
                "candidate_id": "C-1046",
                "message": "Please review",
                "website": "https://bot.example",
            },
        )
        assert spam.status_code == 422
        assert (
            client.post(
                "/api/appeals", json={"candidate_id": "C-1046", "message": "   "}
            ).status_code
            == 422
        )
        assert len(APPEALS) == 0
