# ⚡ ChaosHire — Chaos Simulator for Fair Hiring

> *Netflix breaks its own servers to find weaknesses before customers do. ChaosHire breaks your **hiring AI** the same way — before a regulator, a lawsuit, or a rejected-who-should-have-been-hired candidate does.*

Theme fit: **Inclusive Workforce** (fairness auditing, explainability, appeals) × **chaos engineering** mindset borrowed from resilient-systems thinking.

## What it does

| # | Your feature | Status in this build |
|---|---|---|
| 1 | Upload their AI hiring model **or use yours** | ✅ Upload a CSV of any model's decisions (IP-safe — no model weights needed) **or** audit the two built-in models (`LegacyCorp Screen v1`, `MeritFirst v2`) |
| 2 | Automated bias audits (disparate impact, equal opportunity) | ✅ Per-attribute (gender / ethnicity / age band): selection rates, **disparate impact** (4/5ths rule ≥ 0.8), **demographic-parity gap** (≤ 0.10), **equal-opportunity gap / TPR** (≤ 0.10), with minimum-cell-size guard (n < 30 flagged ⚠, EEOC-style) |
| 3 | Live dashboard of who's filtered out and **why** | ✅ Group bars + XAI reason attribution per rejected candidate (bias-related reasons flagged in red; auditor view shows hidden ground-truth "qualified" losses) |
| 4 | Mitigation suggestions + fairness certificate | ✅ Fairness Certificate Score™ (0–100, A–F, transparent formula) + one-click simulated mitigations: blind screening, proxy removal, threshold calibration → instant before→after re-audit |
| 5 | Candidate-facing appeal portal | ✅ Candidate looks up their application ID → sees decision, score, plain-language reasons → files appeal → HR queue with **auto-triage** ("HIGH — qualified candidate rejected") |
| ⭐ | The differentiator: **Chaos Lab** | ✅ 5 chaos tests: Gender-Swap Counterfactual, Name/Community-Swap Counterfactual, Privilege-Keyword Injection, Career-Gap Stress, Ageing Stress → 0–100 Chaos Resilience Score |

## Tech

- **Backend:** Python · FastAPI · NumPy · Pandas (fairness metrics, counterfactual simulation, mitigation simulation all hand-rolled — easy to explain to judges)
- **Frontend:** single-file vanilla JS dashboard, zero external CDN dependencies
- **Data:** 1,000 synthetic candidates with hidden ground-truth `qualified` labels; two built-in models — a subtly-biased vendor model and a skills-only fair baseline

## Run it

```bash
pip install fastapi uvicorn numpy pandas
python3 -m uvicorn backend:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

## 3-minute demo script for judges

1. **Hook (30s):** "Amazon scrapped its hiring AI because it punished résumés containing the word 'women's'. Every company now runs models like this — and almost none can prove they're fair. ChaosHire is the proving ground."
2. **The audit (30s):** Dashboard on `LegacyCorp Screen v1` → certificate **42 / Grade F**, gender DI **0.55**, age DI **0.54**, ethnicity DI **0.66** — every attribute fails the four-fifths rule.
3. **The chaos (45s):** Run the Chaos Suite → **16.9% of all decisions flip** on a gender swap, **11.1%** on a name/community swap, age stress kills **33%** of hires. Chaos Resilience **30/100**. *"We found this in 8 seconds. Their regulator would have found it too."*
4. **The human cost (30s):** "Who Got Filtered Out" → **42 qualified candidates** wrongly rejected; top reasons are *age 50+*, *ethnicity*, and *career gap* — not skills.
5. **The fix (30s):** Mitigations → check all three → **42 F → 83 B** live. Then toggle `MeritFirst v2`: **86 B**, chaos resilience **100/100** — proof the platform can also *certify* a good model, not just shame bad ones.
6. **The transparency close (30s):** Candidate portal: look up `C-1046` — **Zara Lopez, 50+, returned from a career break, genuinely qualified, rejected at 0.46 vs the 0.50 bar** — plain-language reasons shown → file appeal → HR queue auto-flags it **"HIGH — qualified candidate rejected"**.
7. **The ask:** "Every hiring model will be audited — by us, or by a court. EU AI Act classifies hiring AI as high-risk; NYC Local Law 144 already mandates bias audits. ChaosHire is compliance and conscience in one box."

## Stretch roadmap (say this when judges ask "what's next")

- Real model upload via ONNX / pickle + SHAP explanations
- LLM-written plain-language decision letters and appeal triage
- Real resume corpus audits; intersectional analysis (gender × ethnicity × age)
- Continuous monitoring with drift alerts; signed, shareable fairness certificates
- Regulatory report export (EU AI Act / NYC LL144 / EEOC formats)
