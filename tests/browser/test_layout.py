"""Every tab must fit both the viewport and its cards at phone and desktop widths.

Regression sweep for three layout bugs found by opening every tab at
1440/1280/1024/768/390/320px in Chromium:

1. the Fairness Dashboard score card let the 210px text column beside the
   120px score ring spill past the card (and the page scrolled sideways at
   1024px and 320px);
2. on phones the Upload tab's ``<pre id="schema">`` stretched the ``.g2``
   track (``1fr`` is ``minmax(auto,1fr)``), so both cards became as wide as
   the longest schema line and the page scrolled ~800px sideways;
3. the same ``1fr`` pattern let a few cards outgrow their track by 4-28px at
   320px (group-fairness, Release Gate and Fairness Review cards).

Two kinds of deliberate overflow are excluded from the card-escape check: the
Appeals honeypot (the "Leave this blank" field sits off-screen on purpose as a
spam trap) and anything inside a horizontally scrollable box (the "Who Got
Filtered Out" table and the schema block scroll inside their own borders by
design).
"""

from __future__ import annotations

from playwright.sync_api import Page, sync_playwright
from test_landing import launch_chromium, running_app

#: (width, height) pairs the layout bugs were originally reported at.
VIEWPORTS = ((1440, 1000), (1024, 800), (390, 844), (320, 700))

#: Every product tab, in the order the nav renders them.
TAB_IDS = (
    "welcome",
    "overview",
    "chaos",
    "filtered",
    "mitigations",
    "appeals",
    "upload",
    "history",
    "compare",
    "agent",
    "demo",
)

#: JS predicate that is true once a tab's content has finished rendering.
#: Five tabs fetch their payload inside ``showTab``; measuring before the
#: fetch resolves would race the loader and only test the spinner card.
TAB_READY = {
    "welcome": "() => !!document.querySelector('#tab-welcome .hero')",
    "overview": "() => !!document.querySelector('#tab-overview .grid')",
    "chaos": "() => !!document.querySelector('#tab-chaos .card')",
    "filtered": "() => !!document.querySelector('#tab-filtered .grid')",
    "mitigations": "() => !!document.querySelector('#tab-mitigations .mit')",
    "appeals": "() => !!document.querySelector('#tab-appeals .appeal-lookup')",
    "upload": "() => !!document.querySelector('#tab-upload #schema')",
    "history": (
        "() => {const s = document.querySelector('#tab-history');"
        "return !!s.querySelector('.history-overflow') || s.textContent.includes('No saved audits yet');}"
    ),
    "compare": "() => !!document.querySelector('#cmpout .grid')",
    "agent": "() => !!document.querySelector('#tab-agent .agent-head')",
    "demo": "() => !!document.querySelector('#tab-demo .demo-steps')",
}

#: Collect every element that escapes its nearest ``.card``. Excluded by
#: design: the honeypot spam trap and content inside overflow-x:auto/scroll
#: boxes (tables and ``<pre>`` blocks scroll within their own borders).
CARD_ESCAPE_PROBE = r"""
() => {
  const escapes = [];
  const rendered = el => {
    const cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  for (const card of document.querySelectorAll('.card')) {
    if (!card.offsetParent && getComputedStyle(card).position !== 'fixed') continue;
    const cr = card.getBoundingClientRect();
    if (cr.width === 0) continue;
    for (const el of card.querySelectorAll('*')) {
      if (el.closest('.honeypot')) continue;
      if (!rendered(el)) continue;
      let scrollable = false;
      for (let p = el.parentElement; p && p !== card.parentElement; p = p.parentElement) {
        if (['auto', 'scroll'].includes(getComputedStyle(p).overflowX)) {
          scrollable = true;
          break;
        }
        if (p === card) break;
      }
      if (scrollable) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      const over = {
        left: Math.max(0, cr.left - r.left),
        right: Math.max(0, r.right - cr.right),
        top: Math.max(0, cr.top - r.top),
        bottom: Math.max(0, r.bottom - cr.bottom),
      };
      if (Math.max(over.left, over.right, over.top, over.bottom) > 1) {
        escapes.push({
          tag: el.tagName.toLowerCase(),
          cls: String(el.className).slice(0, 60),
          over,
          text: (el.textContent || '').trim().slice(0, 40),
        });
      }
    }
  }
  return escapes;
}
"""


def _assert_tab_fits(page: Page, width: int, tab: str) -> None:
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    escapes = page.evaluate(CARD_ESCAPE_PROBE)
    details = "; ".join(
        f"<{item['tag']} class={item['cls']!r}> sticks out {item['over']} (…{item['text']!r})"
        for item in escapes[:6]
    )
    assert overflow <= 0, f"{width}px {tab}: page scrolls sideways by {overflow}px"
    assert not escapes, f"{width}px {tab}: content escapes its .card: {details}"


#: Group button that reveals each section. Home stays outside the five-tab bar.
SECTION_GROUP = {
    "overview": "measure",
    "filtered": "measure",
    "chaos": "chaos",
    "mitigations": "review",
    "appeals": "review",
    "upload": "data",
    "history": "data",
    "compare": "review",
    "agent": "review",
    "demo": "demo",
}


def open_section(page: Page, tab: str) -> None:
    """Open a product section through the grouped navigation."""
    if tab == "welcome":
        page.locator("#home-tab").click()
        return
    page.locator(f'#tabs button[data-t="{SECTION_GROUP[tab]}"]').click()
    sub = page.locator(f'#subnav button[data-t="{tab}"]')
    if sub.count():
        sub.click()


def test_every_tab_fits_the_viewport_and_its_cards() -> None:
    with running_app() as url, sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        try:
            for width, height in VIEWPORTS:
                context = browser.new_context(
                    viewport={"width": width, "height": height}, service_workers="block"
                )
                page = context.new_page()
                page.goto(url, wait_until="load")
                page.wait_for_selector("#tabs button[data-t='demo']", timeout=15_000)
                for tab in TAB_IDS:
                    open_section(page, tab)
                    page.wait_for_function(TAB_READY[tab], timeout=30_000)
                    _assert_tab_fits(page, width, tab)
                context.close()
        finally:
            browser.close()
