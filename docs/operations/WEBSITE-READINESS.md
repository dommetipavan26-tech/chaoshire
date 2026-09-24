# Website readiness and page-speed check

This document audits the public-facing ChaosHire **synthetic prototype**. It is not a production privacy certification or a Lighthouse field-data report. The Render service is hand-managed, so a code or Blueprint change does **not** prove a setting has reached the live service.

## What is implemented

| Checklist area | Status in this codebase |
|---|---|
| Privacy Policy and Terms & Conditions | Separate `/privacy` and `/terms` pages, linked from the site footer. The owner must review the contact method, actual deployment retention, and legal wording before publication. |
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

## Live verification snapshot — 24 September 2026

The source changes **have not reached** the existing Render deployment. The live `/api/ready` returned `{"status":"ready","database":"available"}`, but live `/api/meta` still advertised **270 tests / 94.7% coverage** versus **281 / 94.8%** in this checkout. Requests to the live `/privacy`, `/terms`, `/robots.txt`, `/sitemap.xml`, and `/social-preview.png` returned `{"detail":"Not Found"}`; the home page still showed the older CTA and proof figures. Locally, all five new routes return 200 with the expected content types.

Direct `curl` requests to the public HTTPS host failed a TLS handshake **from this sandbox**; an independent web fetcher could reach the live API. That sandbox-specific error does **not** establish a live TLS fault, but it prevents independent verification here of HTTP→HTTPS redirects, HSTS response headers, and production timing. The owner must check these from another network after deploying. No live analytics consent, external links, or legal contact channel was verified. The local suite passed **281 tests / 94.8% coverage**, the opt-in browser suite passed **4 tests**, and 21 local axe audits reported no violations (8 had clipped elements needing manual contrast review). A repeat five-run local speed sample measured 33 ms desktop / 30 ms 390px load events; these are not production figures.

## Owner checks before the live rollout

1. Review privacy/terms wording and a contact path for the entity operating the service. Do not accept real applicant data on the public demo.
2. On the **existing hand-managed Render service**, confirm the generated API key remains server-side; verify `RENDER_SERVICE_ID`/`RENDER_EXTERNAL_URL`, `CHAOSHIRE_PUBLIC_ORIGIN`, HTTPS enforcement, and proxy-header behaviour. `render.yaml` alone does not update that service. Test `curl -I http://chaoshire.onrender.com/privacy` for a HTTPS redirect and `curl -I https://chaoshire.onrender.com/privacy` for HSTS; `/api/ready` must still return 200.
3. Verify the deployed robots/sitemap and preview image, and inspect link previews in the target social networks. Check external URLs manually; the repository tests only validate same-site links and files.
4. With consent rejected, inspect browser Network to confirm **no** `/api/analytics/view` call. With consent allowed, confirm a page-section count is visible to an operator via authenticated `GET /api/ops/analytics`. Keep `X-API-Key` out of the browser and published documentation.
5. Repeat a real-device audit for contrast, touch targets, horizontal scrolling, keyboard navigation, and page load across a cold Render instance. Use an independent legal/security review before handling personal data or making production hiring decisions.
