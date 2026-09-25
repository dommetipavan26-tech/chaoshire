# Website readiness and page-speed check

This document audits the public-facing ChaosHire **synthetic prototype**. It is not a production privacy certification or a Lighthouse field-data report. The Render service is hand-managed, so a code or Blueprint change does **not** prove a setting has reached the live service.

## What is implemented

| Checklist area | Status in this codebase |
|---|---|
| Privacy Policy and Terms & Conditions | Separate `/privacy` and `/terms` pages, linked from the site footer. Their private contact route is GitHub's private vulnerability reporting (**Report a vulnerability** on the repository's Security tab), which must stay enabled. Wording reviewed for the synthetic demo on 24 September 2026; it is not a substitute for independent legal review before handling real personal data. |
| Secrets and HTTPS | Operator, connector, and webhook credentials remain in server environment variables; a canary test checks public HTML/CSS/API metadata for leaks. On Render (or with `CHAOSHIRE_FORCE_HTTPS=1`) public HTTP redirects to a configured HTTPS origin, and secure responses carry HSTS. Health probes are exempt from redirects. Never trust forwarded scheme headers outside a proxy that overwrites them. |
| Consent and analytics | Accessible, optional, cookie-free consent banner. No page-view request occurs before Allow. The choice is stored in localStorage and can be changed in the footer. Only allowlisted section names reach the first-party API; daily counts are operator-only, process-local, and expire within 30 UTC days or on restart. No visitor IDs are stored with those counts. |
| Search and sharing | Distinct page titles/descriptions, canonical HTTPS URLs, Open Graph/Twitter preview with alt text, 1200×630 PNG, `/favicon.ico` + PNG favicon, `/sitemap.xml`, and `/robots.txt` (excludes API/docs). |
| Accessible and mobile UI | One primary action (**Start the 3-minute demo**); mobile shows all three model choices without horizontal page overflow. Form labels, inline error messages, keyboard access, reduced-motion styles, and legible colours are checked in a real browser. API errors remain JSON; browser navigation gets a useful HTML 404. |
| Links and forms | Internal site and current Markdown relative links checked by tests. Appeals and CSV upload forms validate required fields and sizes before posting; server-side schemas remain authoritative. Public appeals also have a honeypot and existing per-client/instance rate limits. This is not a CAPTCHA or a defence against determined bots. |

## Local speed and accessibility measurements

Measured **24 September 2026** with headless Chromium against a locally running Uvicorn app. Five uncached visits per width, each in a fresh browser context with service workers blocked; median timings:

| Viewport | TTFB | Load event | First contentful paint | Observed largest contentful paint | HTML on wire / decoded | Other resources on wire |
|---|---:|---:|---:|---:|---:|---:|
| 1440px | 5 ms | 31 ms | 76 ms | 76 ms | 17,239 / 55,867 bytes | 10,270 bytes |
| 390px | 5 ms | 28 ms | 56 ms | 56 ms | 17,239 / 55,867 bytes | 10,270 bytes |

`GZipMiddleware` compresses the HTML shell and CSS; the assets figure includes loaded CSS/API resources but **not** the main HTML response. The 320px browser regression also reports no document-wide horizontal overflow and verifies the consent banner cannot cover the CTA when scrolled into view. These sandbox timings are **not** Render cold-start times, a mobile-network benchmark, Indian field Core Web Vitals, or a Lighthouse score. INP and CLS were not measured. Measure the deployed host separately.

Axe-core **4.10.3** checked Home, Dashboard, Upload, Appeals, Privacy, Terms, and the 404 page at **1440/390/320px**: **0 violations across 21 audits**. Eight audits marked some colour-contrast elements *inconclusive* because they were partly clipped by the viewport, not as passes. The automated WCAG AA palette test separately checks all text tokens on all site backgrounds (lowest pair, rose on the lighter card: **5.82:1**; muted text there: **6.0:1**) and the primary button (**7.77:1**). Manual review remains necessary for clipped text, keyboard/screen-reader behaviour, and real devices.

Reproduce with a running app and `requirements-browser.txt` + Playwright Chromium installed:

```bash
python scripts/check_page_speed.py --base-url http://127.0.0.1:8000 --runs 5
curl -fLsS https://registry.npmjs.org/axe-core/-/axe-core-4.10.3.tgz \
  | tar -xzO package/axe.min.js > /tmp/chaoshire-axe.min.js
python scripts/check_accessibility.py --axe-path /tmp/chaoshire-axe.min.js
python -m pytest tests/browser -q   # browser suite is opt-in, not in the default test count
```

For custom Chromium binaries, pass `--chromium-executable PATH` to both scripts. JSON evidence is saved in ignored `reports/generated/page-speed.json` and `reports/generated/accessibility.json`. The default suite verifies mobile contrast tokens, form behaviour, SEO routes, relative links, and consent gating; external links and the hand-managed live service require the owner checks below.

## Automated live checks

A merge does not prove a deploy on the hand-managed service, so [`.github/workflows/live-site.yml`](../../.github/workflows/live-site.yml) checks the running site from GitHub's servers. It runs after every push to `main` and can be started by hand (**Actions → Live site checks → Run workflow**) after a manual Render deploy. It first waits (30 minutes after a push; 10 by default when run by hand) until the live `/api/meta` build facts and stylesheet version match the commit. Then [`scripts/check_live_site.py`](../../scripts/check_live_site.py) verifies:

- the new routes, content types, titles, robots/sitemap origin, and the 1200×630 social card;
- the HTTP→HTTPS redirect target, HSTS of at least one year, CSP without `unsafe-inline`, and the framing/sniffing/referrer headers;
- that analytics rejects a non-allowlisted page (422, not counted) and hides counts without the operator key (401);
- every link on the home, privacy, and terms pages;
- in Chromium, at 1440/390/320px: no horizontal overflow while clicking through every product tab (Home to Guided Demo), all three model choices visible, no analytics beacon before a choice, and correct Reject/Allow behaviour (the beacon is intercepted, so production counts are untouched);
- warm server timings and real-browser page speed, then a second job times a cold start after 17 idle minutes (Render's free instance spins down after 15).

A site still serving an older build is reported as a warning, not a failure. Results appear as annotations and job summaries, and screenshots are kept as the `live-site-evidence` artifact. The same checks run locally with `python scripts/check_live_site.py --base-url https://chaoshire.onrender.com`.

## Live verification snapshot — 24 September 2026

[Live site checks run #1](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/35996308542) (the push after PR #38) passed **every** check against the hand-deployed Render service, which reported this release's build facts (v0.24.0, 281 tests, 94.8%, stylesheet digest matching that commit):

- all 11 routes returned the expected status and content type; privacy, terms and 404 pages carried their titles; robots.txt and sitemap.xml advertised the `https://chaoshire.onrender.com` origin; the social card is a 1200×630 PNG declared as `og:image`;
- `http://chaoshire.onrender.com/privacy` redirected with 301 to the HTTPS origin, HTTPS `/api/ready` returned 200, HSTS was `max-age=31536000`, and the CSP (no `unsafe-inline`, `frame-ancestors 'none'`), `x-frame-options`, `nosniff` and `no-referrer` headers were all in place;
- the analytics gate rejected a non-allowlisted page with 422 (nothing counted) and hid counts without the operator key (401);
- all 14 checked links resolved (9 on this site, the rest external) across `/`, `/privacy`, and `/terms`;
- in Chromium at 1440/390/320px the home page and `/privacy` showed no horizontal overflow and all three model choices were visible; no analytics beacon fired before a choice, and Reject/Allow behaved as specified (the beacon is intercepted, so production counts were untouched);
- warm server medians were 206 ms to first byte on `/` (5 warm requests), and real-browser medians of three fresh visits were 335 ms TTFB / 724 ms load at 1440px and 226 ms TTFB / 450 ms load at 390px, with 16.8 KB of HTML on the wire. These are warm GitHub-runner measurements, not Indian field Core Web Vitals, a mobile-network benchmark or a Lighthouse score.

The cold-start job did **not** capture a real cold start: the free instance stayed awake through the 17 idle minutes and answered the "cold" `GET /` in 0.33 s (the warm control answered in 0.28 s). Run **Actions → Live site checks → Run workflow** with **measure cold start** after Render logs a spin-down if a boot figure is needed; do not quote the 0.33 s as a cold start.

The three layout fixes in this revision (score-card text column, phone-width Upload cards, narrow grid cards) landed after run #1 and will be covered by the next live run after the following deploy. Against this revision locally the full suite still passes 281 tests / 94.8% coverage, the opt-in browser suite passes five tests — including a new sweep that opens every tab at 1440/1024/390/320px and fails on sideways scrolling or content escaping a card — and 21 local axe audits report no violations (6 pages keep clipped elements that need manual contrast review).

## Owner checks before the live rollout

1. Keep private vulnerability reporting enabled (**Settings → Advanced Security**); both legal pages and `SECURITY.md` link to its **Report a vulnerability** form. Re-review the privacy/terms wording before accepting any real personal data; do not accept real applicant data on the public demo.
2. On the **existing hand-managed Render service**, confirm the generated API key remains server-side; verify `RENDER_SERVICE_ID`/`RENDER_EXTERNAL_URL`, `CHAOSHIRE_PUBLIC_ORIGIN`, HTTPS enforcement, and proxy-header behaviour. `render.yaml` alone does not update that service. Test `curl -I http://chaoshire.onrender.com/privacy` for a HTTPS redirect and `curl -I https://chaoshire.onrender.com/privacy` for HSTS; `/api/ready` must still return 200.
3. Verify the deployed robots/sitemap and preview image, and inspect link previews in the target social networks. Check external URLs manually; the repository tests only validate same-site links and files.
4. With consent rejected, inspect browser Network to confirm **no** `/api/analytics/view` call. With consent allowed, confirm a page-section count is visible to an operator via authenticated `GET /api/ops/analytics`. Keep `X-API-Key` out of the browser and published documentation.
5. Repeat a real-device audit for contrast, touch targets, horizontal scrolling, keyboard navigation, and page load across a cold Render instance. Use an independent legal/security review before handling personal data or making production hiring decisions.

## Night Ledger (this revision)

This revision replaces the lab-console skin with a bound-audit look: warm
near-black paper (`#1c1714`), cream text, a brass rule, and one self-hosted
heading face (Besley, Latin subset, SIL OFL, `chaoshire/web/static/fonts/`).
The eleven sections are five groups, with Guided Demo first. The three audit
models are a persistent strip above the navigation — large cards on a wide
screen (name, grade, one-line role), full-width rows on a phone — so they are
not buried in the finding card. The selected model carries a brass rule and a
check. LegacyCorp stays 32/F, MeritFirst 84/B, TalentFit 66/C. The landing
page still leads with one finding (Zara Garcia, C-1489, 169 gender flips)
instead of four feature cards. Build facts
stay in the footer and still come from `/api/meta`. The privacy choice is a
slim bar fixed to the bottom; nothing is counted before Reject or Allow.
Element IDs the tests use are unchanged.

Before/after evidence, captured with consent already dismissed so the fixed
bar is not painted over the page:
`docs/portfolio/assets/redesign-{before,after}-{desktop,mobile}.png`.
"Before" is the previous lab-console revision. "After" is Night Ledger before
the audit-model strip moved above the navigation. The current landing shots
are `docs/portfolio/assets/landing-{desktop,mobile}.png`.
`scripts/capture_redesign.py` uses the same viewport and scale for both labels.

Measured locally on 25 September 2026 against a running Uvicorn app (headless
Chromium, fresh context, service workers blocked):

- Tests: `281` collected (`276` passed here, `5` skipped without scikit-learn);
  the committed counts stay `281` tests and `94.8%` package coverage. The five
  opt-in browser tests pass, including the every-tab sweep.
- axe-core 4.13.0, 21 audits (Home, Dashboard, Upload, Appeals, Privacy, Terms,
  and 404 at 1440/390/320): **0 violations**. Colour-contrast on the consent
  bar is decidable: the bar, its actions, and its buttons use an opaque
  `#241e19` fill, and the privacy link is a sibling of the one-line notice
  rather than a nested run of text.
- Token contrast: lowest required pair `--rose` on `--card2` is 5.87:1.
  Button text `#1c1714` on `--blue` (`#f3ebdf`) is 15.02:1.
- Layout: 0px horizontal overflow at 1440/1366/1024/768/390/320. At 1366×768
  and 390×844 the headline and "Start the 3-minute demo" sit above the
  consent bar without scrolling. Rechecked after the audit-model strip moved
  above the navigation: same fold, still 0px of horizontal overflow at those
  widths.
- Page speed (median of 5): 1440px TTFB 6 ms / load 75 ms / FCP 120 ms /
  LCP 120 ms, HTML 17,961 B on the wire, other resources 30,332 B (the
  self-hosted face is 18,604 B). 390px TTFB 5 ms / load 52 ms / FCP 68 ms /
  LCP 68 ms. Timings stay well under a second. The extra asset bytes are the
  required same-origin font; CSP does not allow a font CDN.

The previous lab-console measurements (axe-core 4.10.3, 1440px FCP 68 ms)
remain in the git history of this file.
