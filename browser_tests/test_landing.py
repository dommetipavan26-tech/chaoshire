"""Landing page, navigation, mobile layout and keyboard behaviour in a real browser."""
from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.browser

GITHUB = "https://github.com/dommetipavan26-tech/chaoshire"


def test_landing_is_the_first_screen_and_states_the_problem(page):
    assert page.locator("#landing").is_visible()
    assert page.locator("#app").is_hidden()

    headline = page.locator("h2").first.inner_text()
    assert "identity" in headline.lower()

    problem = page.locator(".lprob").inner_text()
    assert "ChaosHire also flips" in problem
    assert "gender, community, age and career-gap markers" in problem

    # Nothing in the recruiter's first screen may hide a scroll.
    hero_box = page.locator(".lhero").bounding_box()
    assert hero_box is not None and hero_box["height"] > 400


def test_landing_offers_both_entry_points_and_evidence_links(page):
    primary = page.get_by_role("button", name=re.compile("Start the guided demo", re.I))
    secondary = page.get_by_role("button", name=re.compile("Explore dashboard", re.I))
    assert primary.is_visible() and secondary.is_visible()
    assert "ghost" not in (primary.get_attribute("class") or ""), "demo CTA should be the primary button"
    assert "ghost" in (secondary.get_attribute("class") or "")
    assert primary.evaluate("el => el.getBoundingClientRect().height") >= 44

    assert page.get_by_role("link", name="Source on GitHub").get_attribute("href") == GITHUB
    assert page.get_by_role("link", name="API docs").get_attribute("href") == "/docs"
    assert page.get_by_role("link", name="Latest release").get_attribute("href") == (
        f"{GITHUB}/releases/latest"
    )


def test_landing_shows_verified_project_statistics(page):
    proof = page.locator("#lproof")
    assert proof.get_attribute("data-verified-tests") == "82"
    assert proof.get_attribute("data-verified-coverage") == "96.83"
    numbers = proof.locator("b").all_inner_texts()
    assert numbers[0] == "82"
    assert numbers[1] == "96.83%"
    assert numbers[2] == "5"
    assert re.fullmatch(r"v\d+\.\d+\.\d+", numbers[3])
    assert "not a legal certification" in page.locator(".lbound").inner_text().lower()


def test_primary_call_to_action_starts_the_guided_demo(page):
    page.get_by_role("button", name="Start the guided demo").click()

    assert page.locator("#landing").is_hidden()
    assert page.locator("#app").is_visible()
    assert page.evaluate("() => location.hash") == "#demo"
    assert page.locator("#tab-demo").is_visible()

    page.locator("#tab-demo .chip", has_text="STEP 1").wait_for()
    steps = page.locator("#tab-demo article.card")
    assert steps.count() == 6
    assert "3-minute portfolio walkthrough" in page.locator("#tab-demo .dim").first.inner_text()


def test_explore_dashboard_button_renders_the_real_audit(dashboard):
    assert dashboard.locator("#tab-overview").is_visible()
    assert "Fairness Risk Score" in dashboard.locator("#tab-overview").inner_text()
    assert dashboard.locator(".grade-ring b").inner_text() == "42"
    assert "LegacyCorp Screen v1" in dashboard.locator("#modelsel").inner_text()
    assert dashboard.locator(".card").count() > 5


def test_visitor_can_return_to_the_landing_view(dashboard):
    dashboard.get_by_role("button", name="Back to overview").click()
    assert dashboard.locator("#app").is_hidden()
    dashboard.get_by_role("button", name="Start the guided demo").click()
    assert dashboard.locator("#tab-demo").is_visible()


def test_hash_deeplinks_open_the_application_directly(context, base_url):
    """A shared link into #chaos must land in the application, not on the landing view.

    Each assertion needs a fresh page: navigating from "/" to "/#chaos" only changes the
    fragment, so the browser never re-runs the boot script.
    """
    chaos = context.new_page()
    chaos.goto(f"{base_url}/#chaos", wait_until="domcontentloaded")
    assert chaos.locator("#landing").is_hidden()
    assert chaos.locator("#tab-chaos").is_visible()
    assert "Chaos Engineering for Fairness" in chaos.locator("#tab-chaos").inner_text()
    assert chaos.evaluate("() => location.hash") == "#chaos"
    chaos.close()

    landing = context.new_page()
    landing.goto(f"{base_url}/#landing", wait_until="domcontentloaded")
    assert landing.locator("#landing").is_visible()
    assert landing.locator("#app").is_hidden()
    landing.close()


def test_keyboard_navigation_reaches_and_activates_the_cta(page):
    page.keyboard.press("Tab")  # skip link
    skip = page.evaluate("() => document.activeElement.textContent")
    assert "Skip to main content" in skip

    page.evaluate("() => document.getElementById('cta-demo').focus()")
    assert page.evaluate("() => document.activeElement.id") == "cta-demo"
    page.keyboard.press("Enter")

    page.locator("#tab-demo article.card").first.wait_for()
    assert page.locator("#app").is_visible()


def test_focus_is_visible_for_keyboard_users(page):
    """Keyboard users need a ring that is not browser-default-only."""
    rules = page.evaluate(
        "() => [...document.styleSheets].flatMap(s => [...s.cssRules])"
        ".filter(r => r.selectorText && r.selectorText.includes(':focus-visible'))"
        ".map(r => r.cssText)"
    )
    assert rules, "no :focus-visible rules found"
    assert any("outline" in rule for rule in rules)
    assert any("outline-width" in rule or "outline:" in rule for rule in rules)


@pytest.mark.parametrize("context", [{"width": 390, "height": 844}], indirect=True)
def test_mobile_viewport_collapses_sections_into_a_drawer(page):
    page.get_by_role("button", name="Explore dashboard").click()
    page.locator("#tab-overview .grade-ring").wait_for()
    assert page.locator("#navtoggle").is_visible(), "the drawer control belongs to the app shell"

    tabs = page.locator("#tabs")
    assert not tabs.is_visible(), "section list should start collapsed on a phone"

    page.get_by_role("button", name=re.compile("Sections", re.I)).click()
    assert tabs.is_visible()
    assert page.get_by_role("button", name="Sections", exact=False).get_attribute("aria-expanded") == (
        "true"
    )

    labels = tabs.locator("button").all_inner_texts()
    assert len(labels) == 10
    for label in ("Guided Demo", "Review Agent"):
        assert any(label in text for text in labels)

    # Touch targets stay finger-sized while the drawer is open.
    heights = page.evaluate(
        "() => [...document.querySelectorAll('#tabs button, #navtoggle')]"
        ".map(el => el.getBoundingClientRect().height)"
    )
    assert len(heights) == 11
    assert min(heights) >= 42

    tabs.get_by_role("button", name="Guided Demo").click()
    assert page.locator("#tab-demo").is_visible()
    assert not tabs.is_visible(), "drawer should close after choosing a section"

    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 1


@pytest.mark.parametrize("context", [{"width": 390, "height": 844}], indirect=True)
def test_mobile_escape_closes_the_drawer(page):
    page.get_by_role("button", name="Explore dashboard").click()
    page.locator("#tab-overview .grade-ring").wait_for()
    page.get_by_role("button", name=re.compile("Sections", re.I)).click()
    assert page.locator("#tabs").is_visible()
    page.keyboard.press("Escape")
    assert not page.locator("#tabs").is_visible()


def test_landing_stays_static_and_does_not_block_on_the_api(page, base_url):
    requests: list[str] = []
    page.on(
        "request",
        lambda request: requests.append(request.url) if "/api/" in request.url else None,
    )
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector("#landing-main")
    assert not [url for url in requests if "meta" in url or "audit" in url], (
        "the landing view should not wait on the waking free-tier server"
    )
