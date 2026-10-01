# Repository audit and completed updates — 1 October 2026

## Outcome

**The implementable engineering updates from the audit are complete and locally verified.** Strict adapter validation, bounded limiter/webhook resources, fail-closed benchmark input, real PostgreSQL tests, distribution installation gates, version constraints, immutable Actions, and declared maintenance tools are now in the working tree.

**This is still a synthetic/portfolio prototype, not production-ready hiring infrastructure.** No user-account/tenant system, managed production storage, independent legal/privacy/security review, or live rollout was invented or silently performed. Those remain explicit owner prerequisites.

| Checkpoint | Result |
|---|---|
| Repository / branch | `dommetipavan26-tech/chaoshire` / `arena/01a0f837-chaoshire` |
| Starting revision | `8015bffeeb15e47f327b80bf490d4140a731f366` |
| Source inventory | **150 files**, including all tracked/non-ignored new files; **0 structural errors/warnings** |
| Python sources | All **84** parsed; configured mypy application/compatibility scope: **30 files**, pass |
| Default suite | **504 tests passed**, separately from optional suites |
| Python coverage | **97.11% measured** (97.1066% unrounded), 2,450 / 2,523 statements covered, 73 missing; floor 90% |
| Committed build facts | `504`, `97.1%` (one-decimal rounding), checked against real collection/coverage |
| Browser suite | **7 passed**, Chromium 153.0.8010.0 / Playwright 1.63.0 |
| Real PostgreSQL | **9 service-backed tests passed**; PostgreSQL 16.2 / psycopg2 2.9.13; **98.53% adapter coverage** in its separate integration run |
| Webhook / decision-contract modules | **100% line coverage** in the default run; stalled-receiver, admission, failure and shutdown regressions included |
| Distributions | Wheel and sdist built; **46 current runtime files** match source; six direct runtime dependencies; `postgres` and `maintenance` extras verified |
| Clean installation | Fresh non-editable runtime-only venv, outside source cwd: API/assets/model/CLI/gates/HTML/PDF/evidence smoke passes |
| Dependency constraints | Linux x86_64 CPython 3.11 and 3.12 resolutions; **82 resolved packages per file**, zero known advisory records in both audits |
| Quality | Ruff lint/format, Node.js syntax, mypy, every-file checker, build-fact drift guard, pip consistency, patch whitespace: pass |
| Static security | Bandit completes with **18 triaged findings: 17 low, 1 medium, 0 high**, no scan errors; not a zero-findings claim |
| Publication / production | Package version stays **0.24.0**. At the local verification checkpoint, no commit, push, release, deployment, real applicant processing or production database write had been performed. These results precede the owner-requested branch publication; they do not claim a main merge or deployment |

Progression: the original source had `312` passing default cases / 95.08% measured coverage; the first audit checkpoint had `379` / 95.25%. The completed update checkpoint is the current baseline above. Scoring algorithms, protected-input policy and the pinned trained artifact were not altered to inflate these figures.

## What “every file” covers

The [every-file inventory](REPOSITORY-INVENTORY.md) gives each source file a responsibility, category, structural checks and result. Discovery uses `git ls-files --cached --others --exclude-standard`, including new files before commit.

Every discovered file is read/hashed and checked according to format: UTF-8/nonempty text, Python AST, JS syntax, TOML/JSON, safe YAML with duplicate-key rejection, workflow triggers/jobs/permissions, current relative Markdown links/headings, HTML IDs/anchors/local assets, CSS references, PNG CRC/dimensions, ICO bounds, WOFF2/header/license notices, safe SVG XML, requirement syntax/includes, and trained-coefficient digest. A limited selected private-key/GitHub/AWS signature check is included; it is not a complete secrets/history scan.

All 12 PNGs and the ICO were decoded with Pillow; fontTools/Brotli decoded the WOFF2 (257 glyphs); the architecture SVG parsed. Existing screenshots are valid historical assets, **not recaptured proof of this revision**.

Ignored environments, caches, generated packages/logs, local `.env`/database state, `.git` internals, and installed third-party source are outside this source inventory. **Structural PASS does not certify each file's entire behavior/security.**

## Organization

| Location | Responsibility | Files |
|---|---|---:|
| Root | Community/license, manifests/package/tool/deployment configuration, stable `backend.py` | 18 |
| `.github/` | Six workflows plus Dependabot | 7 |
| `constraints/` | Reviewable Linux 3.11/3.12 exact-version resolutions | 2 |
| `chaoshire/*.py` | Stable application modules plus shared strict decision contract | 29 |
| `chaoshire/artifacts/` | Unchanged pinned trained-model fixture | 1 |
| `chaoshire/web/` | HTML shell/legal/error pages, separate CSS/JS, licensed font, icons/social image | 15 |
| `tests/` | API/core/infrastructure/web/browser/integration suites and fixtures | 40 |
| `scripts/` | Checks, constraint/distribution tooling, probes and asset maintenance | 12 |
| `examples/` | Synthetic adapter and public benchmark examples | 2 |
| `docs/` | Engineering, operations, planning, portfolio/evidence and index | 24 |

Stable Python import paths, `uvicorn backend:app`, existing API/export compatibility keys and deployment conventions remain intact. Dashboard behavior is in `web/static/chaoshire.js`, not inline in HTML. Shared input validation has its own [decision-contract module](../../chaoshire/decisions.py), avoiding a gratuitous application-wide file move. Historical changelog/task/screenshot records were preserved rather than silently rewritten as current rollout evidence.

## Completed updates

### 1. Strict decision contracts and safer remote connectors

[Shared normalization](../../chaoshire/decisions.py) is used by callable/remote adapters **and every public metric entry point**. The string `"false"` is now False, not truthy qualification. Boolean/numeric 0/1 and documented tokens are accepted; missing/unknown/nonfinite/nonbinary decision or qualification labels fail. Optional scores must be finite numeric values. Requested attributes must exist and be valid; missing group values remain the visible `(missing)` category. Provider frames are copied, not mutated.

Connector auditing supports explicit custom `protected_attributes`. Validation, audit calculation and description all execute inside its protected boundary: malformed vendor output returns **sanitized 502**, not a misleading certificate or internal 500. Invalid operator configuration returns a safe 503.

[Remote configuration](../../chaoshire/adapters.py) now requires:

- HTTPS unless an operator explicitly sets `allow_http: true` for local/private networking.
- No URL userinfo, query strings or fragments; finite positive timeouts no greater than 120 seconds; valid credential-variable names; unique bounded model IDs.
- No bearer-bearing redirect following; bounded identity-encoded response bodies before JSON parsing; bounded row-object collections.
- No raw credential-bearing exception text in responses **or server logs**. Failure class remains available.

These controls do not authorize arbitrary visitor-supplied URLs; endpoint configuration remains a trusted server-only operator boundary.

### 2. Bounded resource behavior

The [limiter](../../chaoshire/platform.py) keeps at most **4,096** identities and lazily removes expired windows on subsequent activity/operator snapshots, without needing that identity to return or a restart. A full map **fails closed** for new identities instead of evicting live budgets and enabling reset attacks. Retry delays round up to the actual expiration. Limits remain process-local, not a distributed multi-instance service.

[Webhook delivery](../../chaoshire/loghook.py) uses **four fixed daemon workers**, **256 total pending plus in-flight reservations**, and a **64 KiB serialized event cap**. Taking work off the queue does not free its reservation until completion. Tests stall the receiver and verify bounded workers/outstanding work, drops, callback failures, flush deadlines, pool sealing and shutdown. Application lifespan performs bounded cleanup; a sealed pool is not replaced while its workers remain alive.

HMAC keys are captured at enqueue time. Receiver bodies are not buffered; redirects/retries are not followed. Failures log class/status only. Unconfigured shipping allocates no worker threads. This remains **best-effort, lossy delivery**, not durable messaging.

New operator-authenticated `GET /api/ops/metrics` exposes bounds/counts without IP identities, URLs, credentials, queued payloads or row data. The existing public `/api/metrics` response shape is retained.

### 3. Fail-closed benchmark data

The [Adult example](../../examples/adult_income_audit.py) now stops **before training** on cached or downloaded digest mismatch. It caps each file at 8 MiB, validates received/declaration sizes and final trusted HTTPS origin, streams hashing, writes a unique temporary file, flushes/fsyncs, verifies, then atomically replaces the cache. Errors remove partial files and preserve prior cache contents.

`--allow-unverified` is an explicit **experimental** opt-in, not a verified result. Mismatches remain labeled/warned and cannot bypass size bounds. Existing offline synthetic-format tests now opt in explicitly; production/pinned benchmark defaults do not.

### 4. Real PostgreSQL verification and an installable driver extra

`chaoshire[postgres]` / [driver manifest](../../requirements-postgres.txt) declare the actual **psycopg2** driver used by the adapter (not psycopg3). Connections have a five-second connection timeout.

[Opt-in integration tests](../../tests/integration/test_postgres.py) were run against a disposable real PostgreSQL 16.2 server, private Unix socket only, with no production credentials. Each case creates/drops a random schema. They verify schema/index idempotence, Unicode aggregate round-trip, dispatcher paths, ordering/limits, parameterized IDs, commit/rollback/close, constraint recovery, API readiness/history, operator publication, and absence of anonymous persistence/raw rows.

Tests read only **`CHAOSHIRE_TEST_POSTGRES_URL`**, never fall back to the application's DSN, reject nonlocal hosts, and fail rather than skip under `--require-postgres`. The optional suite is separate from the default collected count. CI config includes real PostgreSQL service jobs for both supported Python versions.

### 5. Reproducible dependencies, immutable Actions and package-install gates

- [Version constraints](../../constraints/requirements-py311.txt) and [3.12 resolution](../../constraints/requirements-py312.txt) include runtime/dev/browser/driver/maintenance/build-backend dependencies. Both complete 82-package files were audited without known advisories. They are **version constraints**, not artifact hash locks, universal platform locks or proof of Python 3.12 execution.
- [Constraint compiler](../../scripts/compile_constraints.py) records reviewable resolutions. Broad compatibility ranges remain in library manifests; CI/Docker use the matching Linux resolution. Build backend minimum is a patched setuptools floor and resolves to 84.0.0.
- All external Actions use verified **40-character commit IDs**, with human-readable major-version comments; no mutable major tag alone is trusted.
- [Distribution checker](../../scripts/check_distribution.py) compares wheel/sdist bytes, version/Python/license/CLI/dependency/extra metadata, then installs into a fresh out-of-source runtime-only venv. API/assets/model, backend alias, console/module CLI, passing/blocking gates, HTML/PDF exports and valid/tampered evidence pass.
- Quality/release CI includes that installed-wheel smoke. Container CI is configured to build/run non-root, use a non-default PORT, require healthy `/api/ready`, and fetch packaged assets. **Configuration is not a claim that remote Actions/Docker executed locally.**
- [Maintenance manifest](../../requirements-maintenance.txt) / package extra declare asset/audit/resolution tooling. Development/browser dependencies now prefer HTTPX2 for Starlette TestClient; the old outbound HTTPX runtime remains supported. Clean runtime-only smoke deliberately exercises that older-compatible path too.

## Earlier audit fixes retained

Packaging's invalid/missing `0.0.0` metadata/assets/dependencies was repaired. Actual request bytes are bounded before parsing regardless of declarations; malformed/duplicate lengths return 400, oversized streams 413. Refusals/redirects receive consistent request IDs/security headers/accounting. Unicode keys/digests and noncanonical evidence fail safely. External JS retains nonce/CSP/escaping and content-versioned caches; all HTML templates also invalidate offline cache. Research contrast receives correct certificate objects. Unpublished anonymous uploads download their exact page-local JSON, not another operator's shared slot. The model selector is a named landmark. Pytest's advisory floor, PORT readiness probe and explicit-only font override remain corrected.

The public prototype still intentionally exposes the **latest operator-published aggregate slot** and history to visitors; it is not tenant-specific storage. Anonymous uploads neither publish nor replace it. Audit names and small groups can remain sensitive despite aggregation.

## Verification and limits

### Local executions

| Check | Evidence |
|---|---|
| Full default suite | 504 passed; 97.11% measured coverage; build facts verify 504 / 97.1% |
| Service-backed PostgreSQL | 9 passed; 98.53% adapter coverage (67 / 68 statements) |
| Optional browser | 7 passed: XSS, consent, model selection, research score rendering, local upload download, every-tab layouts |
| Strict every-file checker | 150 files / 0 errors / 0 warnings; 84 Python ASTs and JavaScript syntax |
| Ruff / mypy / pip consistency | Pass; mypy checks 30 application/compatibility files |
| Distribution gates | Pass: 46 runtime files, six direct dependencies, two declared extras, correct 0.24.0 and clean installation |
| Both constraint advisory audits | 82 package versions each, no known advisories at this checkpoint |
| Trained model / holdout | 100% decision agreement and exact digest match; 49-population mean scores unchanged: fair 74.39, original v3 69.49, trained 76.04 |
| Binary assets / XML | Existing image/font/SVG assets decode/parse; font/license notices retained |
| Patch / branch hygiene | Same Arena branch, no whitespace errors, no generated local state tracked, trained artifact unchanged |

All local Python executions used **3.11.2**. PostgreSQL server verification is real but ephemeral/local and on 16.2, **not** a recommendation to deploy that old patch level. Use a current supported/maintained database release for production.

### Accessibility and timing checkpoint

The audit's axe-core 4.13.0 run checked seven pages × 1440/390/320px: **0 reported violations in 21 audits** after the named-landmark fix. Gradient-background colour contrast remains inconclusive on all 21; token palette/layout tests pass but do not establish complete WCAG compliance. Real-device/screen-reader/rendered contrast review remains necessary.

Five fresh local visits per width (service workers blocked) measured median TTFB/load 4/52 ms desktop and 4/55 ms mobile, 2,287/6,896 HTML wire/decoded bytes and 48,294 resource bytes. These are dated **sandbox lab** measurements, not production/cold-start/Lighthouse/field Core Web Vitals. See [website readiness](WEBSITE-READINESS.md) for historical snapshots and owner checks; no fresh performance claim is inferred from the latest backend edits.

### Static findings are not hidden

Bandit reports **18 findings**, with no high severity or scan errors:

- Two low `B105`: noncredential scoring/label literals.
- Two low `B101`: example/screenshot sanity assertions, not authorization guards; replace if promoted into production checks.
- Thirteen low `B404`/`B603`: maintenance subprocess imports/calls using argument lists, not `shell=True`; executable and environment controls are explicit.
- One medium `B310`: the fixed HTTPS UCI downloader, not an arbitrary visitor URL. Its former warning-only integrity behavior is now fail-closed/bounded/atomic and separately regression-tested.

No blanket rule suppression was added. Safe YAML and defused XML remain in the repository checker. This is contextual triage, **not proof of zero security vulnerabilities**.

### Coverage boundaries

Python coverage intentionally excludes synthetic generator `chaoshire/data.py`; JavaScript coverage is not part of the percentage. PostgreSQL remains around 44% in the **default-only** run but reaches 98.53% in the separate real-service suite. Those figures were not combined to inflate the committed default percentage. `__main__.py` remains 0% within pytest's process even though separate module-CLI smoke passes. Mocked/vendor behavior, local server behavior and real production integrations remain different evidence categories.

## Hosted CI follow-up — 2 October 2026

[Pull request #50](https://github.com/dommetipavan26-tech/chaoshire/pull/50) runs the previously prepared gates against the published Arena branch. All ten checks passed for code revision `cedefc7903e6e561c199eb23c8ce8b85fb29ea92`:

| Hosted verification | Evidence |
|---|---|
| Quality / complete default suite / package-install gates, Python 3.11 and 3.12 | [Quality checks](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/36914526740) |
| Real PostgreSQL integration on both Python versions | Same quality workflow, separate service-backed jobs |
| Docker build, non-root UID, non-default PORT, readiness and packaged assets | Same quality workflow, `container-smoke` job |
| Browser/mobile suite | [Browser checks](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/36914527145) |
| Dependency audit and CodeQL analysis / alert gate | [Security checks](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/36914526912) |
| Fairness release gate | [Fairness gate](https://github.com/dommetipavan26-tech/chaoshire/actions/runs/36914526788) |

The initial CodeQL alert concerned a case-sensitive script-tag regex **in a test helper**. It was fixed with structural `HTMLParser` inspection, including mixed-case tags/attributes and closing-tag whitespace coverage, rather than a rule suppression or alert dismissal. The separate CodeQL alert gate now passes.

This hosted evidence closes the earlier **remote CI / Python 3.12 / Docker execution** gaps for the stated code revision. It does not certify a production deployment, real applicant use, external vendor/webhook accounts, tenant isolation, complete secrets/container vulnerability auditing, independent review, or legal/accessibility compliance. PR/main merge and production rollout remain separate actions. Subsequent commits must retain their own green checks; linked historical runs are not relabeled as results for a different SHA.

## Still requires owner decisions / independent execution

1. **Before personal/applicant data:** identity/provider choice, tenant/per-audit authorization and export isolation, approved durable storage, encryption, retention/deletion, backup/restore, incident response and independent legal/privacy/security review. Keep the public demo synthetic until then.
2. **Future revisions / other environments:** hosted CI, Docker and Python 3.12 are now verified for the revision above; repeat those gates after changes. Other platforms, live production configuration and patched production database releases still require their own evidence.
3. **Production Render / proxy / TLS / durability / monitoring:** no live rollout, proxy proof, paid storage, alert-account setup or cold-start test performed. `render.yaml` does not configure an already hand-managed service automatically.
4. **Actual vendor/webhook accounts:** no production credentials/endpoints used. Bounded mocked failure/load tests do not prove an external receiver's contract, throughput or retention policy.
5. **Public Adult benchmark fresh rerun:** the earlier UCI TLS/EOF transport failure prevented real-data re-download. Offline integrity/model tests are valid, but no substituted/fabricated fresh public-benchmark findings are claimed.
6. **Actionlint, complete-history secrets, OS/container/browser scans and independent accessibility/security assessments:** not completed. Workflow YAML/permissions/commit pins were checked; actionlint's release binary transport was blocked.
7. **Noncritical architecture work:** a larger route/workflow decomposition can be a future focused refactor. Stable imports were not moved gratuitously under a nightly correctness update.

These are genuine remaining boundaries, not claims that source updates are unfinished or that production is now certified.

## Repeat / refresh

```bash
# Linux CPython 3.11; use the py312 file for that runtime
python -m pip install -c constraints/requirements-py311.txt -r requirements-dev.txt
python scripts/check_repository.py --require-node --strict
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest --cov=chaoshire --cov-report=term-missing --cov-report=json -q
python scripts/check_build_info.py --coverage-json coverage.json
python -m chaoshire train --check
python -m chaoshire train --holdout
PIP_CONSTRAINT="$PWD/constraints/requirements-py311.txt" python -m build
python scripts/check_distribution.py --wheel dist/chaoshire-*.whl --sdist dist/chaoshire-*.tar.gz \
  --constraints constraints/requirements-py311.txt
python -m pip check
```

Optional services/tools:

```bash
python -m pip install -c constraints/requirements-py311.txt \
  -r requirements-browser.txt -r requirements-examples.txt -r requirements-postgres.txt -r requirements-maintenance.txt
python -m playwright install chromium
python -m pytest tests/browser -q
# Set CHAOSHIRE_TEST_POSTGRES_URL to an explicit disposable LOCAL service first
python -m pytest tests/integration --require-postgres -q \
  --cov=chaoshire.repository_postgres --cov-fail-under=90
python -m pip_audit -r constraints/requirements-py311.txt --no-deps --disable-pip
python -m pip_audit -r constraints/requirements-py312.txt --no-deps --disable-pip
python -m bandit -r chaoshire backend.py scripts examples
python scripts/compile_constraints.py
```

Refresh constraints deliberately, then recheck training, advisories, both runtimes and package installation. They pin reviewed versions but do not provide artifact hash guarantees. Current [task log](../planning/TODO.md), [release checklist](RELEASE-CHECKLIST.md), [persistence notes](PERSISTENCE.md), and [monitoring](MONITORING.md) distinguish completed code from owner rollout prerequisites.

Raw local evidence is ignored under `reports/generated/repository-audit/{baseline,final}/` and `reports/generated/updates-tonight/`. Only source, tests, constraints and report/inventory documents belong in Git; virtual environments, browser/PG tools and local test clusters do not.
