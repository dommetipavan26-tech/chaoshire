# Commits 1 and 2 — the remaining edits

`platform.py`, `state.py`, `repository.py`, `tests/test_security.py` and
`tests/test_demo_hardening.py` ship as complete files. Everything below is a
surgical edit to a file too large to replace safely.

Each block is exact. Search for the **before** text; it appears once.

---

## Commit 1 — security

### `chaoshire/app.py` (2 edits)

```python
# before
from fastapi import Depends, FastAPI, HTTPException, Query

# after
from fastapi import Depends, FastAPI, HTTPException, Query, Request
```

```python
# before
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> HTMLResponse:
    return HTMLResponse(
        content=(PROJECT_ROOT / "index.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache"},
    )

# after
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> HTMLResponse:
    html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
    nonce = getattr(request.state, "csp_nonce", "")
    if nonce:
        # The nonce policy forbids 'unsafe-inline', so the dashboard's single
        # inline script must carry the per-request nonce or it will not run.
        html = html.replace("<script>", f'<script nonce="{nonce}">', 1)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})
```

### `index.html` (4 edits)

**1. The escaper.** This is the fix. `esc` is used inside `title="..."`, where
escaping only `& < >` leaves a break-out reachable from an uploaded CSV cell.

```js
// before
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

// after
const ESC={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
const esc=s=>String(s).replace(/[&<>"']/g,c=>ESC[c]);
```

**2. Escape the chaos-test strings.** Server constants today, but the guarantee
disappears the moment a model id or threshold reaches one of them.

```js
// before
    html+=`<div class="card"><div style="display:flex;justify-content:space-between;gap:10px;align-items:start">
      <h3>${t.name}</h3>${vChip(t.verdict)}</div>
      <p class="dim" style="font-size:13px;margin:6px 0">${t.story}</p>
      <div><span class="dim">${t.metric}:</span> <b>${t.value}</b></div>
      <div class="dim" style="font-size:12.5px;margin-top:4px">${t.detail}</div>

// after
    html+=`<div class="card"><div style="display:flex;justify-content:space-between;gap:10px;align-items:start">
      <h3>${esc(t.name)}</h3>${vChip(t.verdict)}</div>
      <p class="dim" style="font-size:13px;margin:6px 0">${esc(t.story)}</p>
      <div><span class="dim">${esc(t.metric)}:</span> <b>${esc(t.value)}</b></div>
      <div class="dim" style="font-size:12.5px;margin-top:4px">${esc(t.detail)}</div>
```

And the mitigation result list:

```js
// before
    ${r.applied.map(x=>`<div class="grow" style="margin:4px 0"><span class="chip ok">applied</span><span style="font-size:13.5px">${x}</span></div>`).join('')}

// after
    ${r.applied.map(x=>`<div class="grow" style="margin:4px 0"><span class="chip ok">applied</span><span style="font-size:13.5px">${esc(x)}</span></div>`).join('')}
```

**3. The last inline handler.** A nonce policy kills `onclick` silently, so this
button would become dead UI rather than a visible failure.

```js
// before
    $('#tab-overview').innerHTML='<div class="err">The free server was asleep and is still waking up (takes ~60 seconds after being idle).<br><br><button class="btn" onclick="location.reload()">Retry now</button></div>';

// after
    $('#tab-overview').innerHTML='<div class="err">The free server was asleep and is still waking up (takes ~60 seconds after being idle).<br><br><button class="btn" id="retrywake">Retry now</button></div>';
    $('#retrywake').addEventListener('click',()=>location.reload());
```

**4. Stop retrying 4xx.** Small item (b), folded in because it is the same file.
Harmless today (business failures still return 200) and correct once the status
contract lands. Right now a validation error hangs the UI for ~14 seconds.

```js
// before
const jget=async(u)=>{let err;for(let i=0;i<4;i++){try{const r=await fetch(u);if(r.ok)return r.json();err=new Error('HTTP '+r.status);}catch(e){err=e;}await new Promise(s=>setTimeout(s,1400*(i+1)));}throw err;};

// after
const jget=async(u)=>{let err;for(let i=0;i<4;i++){try{const r=await fetch(u);if(r.ok)return r.json();if(r.status<500)return await r.json();err=new Error('HTTP '+r.status);}catch(e){err=e;}await new Promise(s=>setTimeout(s,1400*(i+1)));}throw err;};
```

### `SECURITY.md` — record the residual risk

Replace the content-policy bullet:

```markdown
- Responses include request IDs, security headers, request-size enforcement, and optional rate limiting. `script-src` uses a per-request nonce rather than `'unsafe-inline'`, so an injected `<script>` element cannot execute. `style-src` still allows `'unsafe-inline'` because the dashboard relies on inline `style` attributes, which a nonce does not cover; CSS-based exfiltration is therefore not mitigated. None of these controls have undergone an independent security assessment.
```

### Optional: a behavioural XSS test

The unit tests assert the escaper's shape. This asserts the behaviour. Add to
`browser_tests/test_landing.py` or a new `browser_tests/test_xss.py`:

```python
def test_hostile_group_label_cannot_break_out_of_an_attribute() -> None:
    hostile = '" onmouseover="window.__pwned=1'
    csv = "region,team,decision\n" + "\n".join(
        [f'"{hostile}",alpha,1'] * 30 + ["north,beta,0"] * 30
    )
    with running_app() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.request.post(
            f"{url}/api/upload",
            data={
                "csv": csv,
                "protected_attributes": ["region", "team"],
                "minimum_group_size": 10,
            },
        )
        page.goto(f"{url}/#uploaded", wait_until="networkidle")
        page.evaluate("loadOverview('uploaded')")
        page.get_by_text("Intersectional risks", exact=False).wait_for()
        page.mouse.move(200, 400)
        assert page.evaluate("window.__pwned === undefined")
        browser.close()
```

---

## Commit 2 — demo hardening

### `chaoshire/services.py` (5 edits)

```python
# before
import io
from typing import Any

# after
import io
import os
from typing import Any
```

```python
# before
from .state import APPEALS, UPLOADED, UPLOADED_LOCK

# after
from .state import APPEALS, APPEALS_LOCK, UPLOADED, UPLOADED_LOCK, next_appeal_id
```

**Appeal ids and the bounded queue.**

```python
# before
    record = {
        "id": len(APPEALS) + 1,
        "candidate_id": candidate_id,
        "name": row["name"],
        "gender": row["gender"],
        "message": message,
        "priority": priority,
        "status": "PENDING",
    }
    APPEALS.append(record)
    return {"ok": True, "appeal_id": record["id"], "priority": priority}

# after
    record = {
        "candidate_id": candidate_id,
        "name": row["name"],
        "gender": row["gender"],
        "message": message,
        "priority": priority,
        "status": "PENDING",
    }
    with APPEALS_LOCK:
        # APPEALS is a bounded deque, so positional ids repeat once it wraps.
        record["id"] = next_appeal_id()
        APPEALS.append(record)
    return {"ok": True, "appeal_id": record["id"], "priority": priority}
```

```python
# before
def list_appeals() -> dict[str, list[dict[str, Any]]]:
    return {"appeals": list(reversed(APPEALS))}

# after
def list_appeals() -> dict[str, list[dict[str, Any]]]:
    with APPEALS_LOCK:
        return {"appeals": list(reversed(APPEALS))}
```

**Row cap.** 100,000 rows of arbitrary width is not survivable on a 512MB
instance, and the limit should be deployment-configurable.

```python
# before
    if len(uploaded) > 100_000:
        return {"error": "The public prototype accepts at most 100,000 rows per audit."}

# after
    maximum_rows = max(1, int(os.getenv("CHAOSHIRE_MAX_UPLOAD_ROWS", "50000")))
    if len(uploaded) > maximum_rows:
        return {"error": f"This deployment accepts at most {maximum_rows:,} rows per audit."}
```

**Discard the raw frame.** The highest-value change in this commit. Confirm
nothing reads it first:

```bash
grep -rn 'UPLOADED\["df"\]' --include='*.py' .
```

Only the writer, the resets and the tests should appear.

```python
# before
    with UPLOADED_LOCK:
        UPLOADED["df"] = uploaded
        UPLOADED["metadata"] = metadata
        UPLOADED["audit"] = result

# after
    with UPLOADED_LOCK:
        # The parsed frame is deliberately discarded. Nothing reads it once the
        # audit is built, so uploaded rows never outlive the request that
        # carried them, and a large upload cannot pin memory for the life of
        # the process.
        UPLOADED["df"] = None
        UPLOADED["metadata"] = metadata
        UPLOADED["audit"] = result
```

Also update the `uploaded_audit` docstring, which currently promises the rows
are retained:

```python
# before
    raw rows never leave the uploading process's memory.

# after
    raw rows are discarded when the upload request completes.
```

### `chaoshire/schemas.py` (1 edit)

```python
# before
class AppealRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=5000)

# after
class AppealRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    # 5,000 characters on an open endpoint with an unbounded queue was a
    # memory-growth path; 1,000 is ample for an appeal note.
    message: str = Field(min_length=1, max_length=1000)
```

### `tests/conftest.py` (replace whole file)

```python
"""Shared test isolation for in-memory application state and SQLite history."""
import pytest

from chaoshire import state
from chaoshire.platform import LIMITER
from chaoshire.state import UPLOADED


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DB_PATH", str(tmp_path / "chaoshire-test.db"))
    state.reset_appeals()
    LIMITER.reset()
    UPLOADED.update({"df": None, "metadata": None, "audit": None})
    yield
    state.reset_appeals()
    LIMITER.reset()
    UPLOADED.update({"df": None, "metadata": None, "audit": None})
```

`tests/test_verification_fixes.py` and `tests/test_repository.py` still import
`APPEALS` and `UPLOADED` directly and keep working: the deque is cleared in
place and the dict is updated in place.

### `chaoshire/cli.py` — the purge hook

In `build_parser`:

```python
    history = commands.add_parser("history", help="List or purge stored aggregate audits")
    history.add_argument("--purge", metavar="AUDIT_ID", help="delete one stored audit")
    history.add_argument("--limit", type=int, default=20)
```

In `main`, before the audit is built (the `history` command needs no model):

```python
    if args.command == "history":
        from .repository import delete_audit, list_audits

        if args.purge:
            removed = delete_audit(args.purge)
            print(f"{'Deleted' if removed else 'No such audit:'} {args.purge}")
            return 0 if removed else 1
        print(json.dumps(list_audits(args.limit), indent=2))
        return 0
```

### `render.yaml`

```yaml
# before
      - key: CHAOSHIRE_RATE_LIMIT_PER_MINUTE
        value: "0"

# after
      - key: CHAOSHIRE_RATE_LIMIT_PER_MINUTE
        value: "30"
      - key: CHAOSHIRE_MAX_UPLOAD_ROWS
        value: "50000"
      - key: CHAOSHIRE_MAX_AUDIT_ROWS
        value: "200"
      - key: CHAOSHIRE_MAX_APPEALS
        value: "200"
```

### `.env.example`

```bash
# Platform safeguards. The public demo accepts unauthenticated writes, so these
# bounds are what stop a visitor growing memory or disk without limit.
CHAOSHIRE_MAX_BODY_BYTES=5500000
CHAOSHIRE_RATE_LIMIT_PER_MINUTE=30
CHAOSHIRE_MAX_UPLOAD_ROWS=50000
CHAOSHIRE_MAX_AUDIT_ROWS=200
CHAOSHIRE_MAX_APPEALS=200

# Rate limiting reads the first X-Forwarded-For entry so visitors behind the
# platform proxy do not share one bucket. Set to 0 if the app is ever exposed
# without a trusted proxy in front of it, since the header is client-supplied.
CHAOSHIRE_TRUST_FORWARDED_FOR=1
```

### `docs/PERSISTENCE.md`

```markdown
# before
The raw parsed DataFrame remains in process memory only so the current session can render and export its aggregate audit. A restart clears those rows.

# after
The raw parsed DataFrame is discarded when the upload request completes. Only the aggregate audit is retained in the shared slot, so uploaded rows never outlive the request that carried them.
```

Add a retention paragraph:

```markdown
## Retention

The history table is trimmed to the newest `CHAOSHIRE_MAX_AUDIT_ROWS` records
(default 200) after every write, because the public demo accepts
unauthenticated uploads with a caller-supplied audit name. `python -m chaoshire
history --purge AUD-...` removes a single record without a redeploy.
```

### `SECURITY.md` — the same correction

```markdown
# before
- Raw uploaded CSV rows and appeals are stored in process memory.

# after
- Raw uploaded CSV rows are discarded when the upload request completes; only the aggregate audit is kept in memory. Appeals are held in a bounded in-memory queue (default 200) and are lost on restart.
```

---

## Verify

```bash
python -m ruff check .
python -m pytest -q
python -m pytest tests/test_security.py tests/test_demo_hardening.py -v
```

Expected: all green, two new files, no existing test touched except
`tests/conftest.py`. If `test_v020_contract_and_operational_endpoints` drifts on
its `metrics["requests"] >= 2` assertion, that is the new rejection accounting
working — the assertion is a lower bound, so it should still pass.

## Manual check after deploy

```bash
curl -sI https://chaoshire.onrender.com/ | grep -i content-security-policy
# script-src must contain 'nonce-...' and must not contain 'unsafe-inline'

for i in $(seq 1 35); do
  curl -s -o /dev/null -w '%{http_code} ' https://chaoshire.onrender.com/api/health
done
# the last few should be 429
```
