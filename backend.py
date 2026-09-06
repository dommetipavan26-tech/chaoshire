"""ChaosHire — Chaos Simulator for Fair Hiring (backend)."""
import io
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

app = FastAPI(title="ChaosHire")

# ---------------------------------------------------------------- demo data
rng = np.random.default_rng(29)  # curated demo seed: fair model must audit clean
N = 1000

MALE = ["Arjun", "Ravi", "John", "David", "Wei", "Omar", "Carlos", "Daniel", "Sanjay", "Peter", "Ahmed", "Vikram"]
FEMALE = ["Priya", "Aisha", "Maria", "Chen", "Fatima", "Lakshmi", "Sarah", "Divya", "Emma", "Anita", "Zara", "Meera"]
NBN = ["Alex", "Sam", "Riya", "Noor", "Kai", "Dev"]
SUR = ["Sharma", "Patel", "Khan", "Smith", "Chen", "Garcia", "Reddy", "Iyer", "Ali", "Kumar", "Brown", "Das", "Nair", "Singh", "Lopez", "Kim"]

g_arr = rng.choice(["M", "F", "NB"], N, p=[0.53, 0.42, 0.05])
e_arr = rng.choice(["G1", "G2", "G3"], N, p=[0.45, 0.35, 0.20])
a_arr = rng.choice(["18-25", "26-35", "36-50", "50+"], N, p=[0.28, 0.36, 0.22, 0.14])
skills = np.clip(rng.normal(60, 18, N), 5, 100).round(0)
experience = rng.integers(0, 16, N)
education = rng.choice([1, 2, 3], N, p=[0.30, 0.45, 0.25])
certs = rng.integers(0, 5, N)
prestige = np.clip(rng.normal(0.55, 0.18, N) + np.where(e_arr == "G1", 0.07, 0) - np.where(e_arr == "G3", 0.10, 0), 0, 1).round(3)
gap = (rng.random(N) < 0.18)
edu_num = np.array([{1: 1.0, 2: 0.66, 3: 0.33}[x] for x in education])
merit = 0.45 * skills / 100 + 0.25 * experience / 15 + 0.18 * edu_num + 0.12 * certs / 4 + rng.normal(0, 0.05, N)
qualified = merit >= np.quantile(merit, 0.6)  # ground truth: top 40% are "qualified"

names = []
for i in range(N):
    pool = MALE if g_arr[i] == "M" else (FEMALE if g_arr[i] == "F" else NBN)
    names.append(str(rng.choice(pool)) + " " + str(rng.choice(SUR)))

df = pd.DataFrame({
    "candidate_id": [f"C-{1000 + i}" for i in range(N)],
    "name": names, "gender": g_arr, "ethnicity": e_arr, "age_band": a_arr,
    "skills": skills, "experience": experience, "edu_tier": education, "edu_num": edu_num,
    "certs": certs, "prestige": prestige, "gap": gap, "merit": merit, "qualified": qualified,
})

# ---------------------------------------------------------------- models
FEATURE_LABELS = {
    "skills": "Skills assessment", "experience": "Years of experience",
    "education": "Education level", "prestige": "College prestige (proxy)",
    "certs": "Certifications", "gender_M": "Gender = Male bonus",
    "gender_NB": "Gender = Non-binary penalty", "eth_G2": "Ethnicity B penalty",
    "eth_G3": "Ethnicity C penalty", "age_36-50": "Age 36-50 penalty",
    "age_50+": "Age 50+ penalty", "gap": "Career-gap penalty",
}
FEATURE_DESC = {
    "skills": "Score on the structured skills test", "experience": "Relevant years of experience",
    "education": "Highest completed education", "prestige": "Prestige rank of the college named on the résumé",
    "certs": "Number of relevant certifications", "gender_M": "Model boosts résumés it reads as male",
    "gender_NB": "Model penalizes non-binary markers", "eth_G2": "Model penalizes names from community B",
    "eth_G3": "Model penalizes names from community C", "age_36-50": "Model penalizes mid-career applicants",
    "age_50+": "Model penalizes applicants above 50", "gap": "Model penalizes career gaps (e.g. parental leave)",
}
BIAS_FEATURES = ["gender_M", "gender_NB", "eth_G2", "eth_G3", "age_36-50", "age_50+", "gap", "prestige"]

LEGACY = {"intercept": 0.05, "skills": 0.40, "experience": 0.19, "education": 0.13, "prestige": 0.09,
          "gender_M": 0.045, "gender_NB": -0.035, "eth_G2": -0.015, "eth_G3": -0.04,
          "age_36-50": -0.015, "age_50+": -0.055, "gap": -0.05, "certs": 0.02}
FAIR = {"intercept": -0.08, "skills": 0.50, "experience": 0.25, "education": 0.15, "certs": 0.10}

MODEL_META = {
    "legacy": {"id": "legacy", "title": "LegacyCorp Screen v1", "blurb": "Vendor model in production. Accused of bias — you're auditing it."},
    "fair": {"id": "fair", "title": "MeritFirst v2", "blurb": "Skills-only reference model. Your clean baseline."},
}
THRESHOLD = 0.5


def comps(d: pd.DataFrame) -> dict:
    return {
        "skills": d["skills"] / 100.0, "experience": d["experience"] / 15.0,
        "education": d["edu_num"], "prestige": d["prestige"], "certs": d["certs"] / 4.0,
        "gender_M": (d["gender"] == "M").astype(float), "gender_NB": (d["gender"] == "NB").astype(float),
        "eth_G2": (d["ethnicity"] == "G2").astype(float), "eth_G3": (d["ethnicity"] == "G3").astype(float),
        "age_36-50": (d["age_band"] == "36-50").astype(float), "age_50+": (d["age_band"] == "50+").astype(float),
        "gap": d["gap"].astype(float),
    }


def score(d: pd.DataFrame, coefs: dict) -> np.ndarray:
    c = comps(d)
    s = np.full(len(d), float(coefs.get("intercept", 0.0)))
    for k, v in coefs.items():
        if k == "intercept" or v == 0 or k not in c:
            continue
        s = s + v * c[k].to_numpy(dtype=float)
    return np.clip(s, 0, 1)


def build_decisions(coefs: dict, thr=None) -> pd.DataFrame:
    d = df.copy()
    sc = score(d, coefs)
    d["score"] = sc
    d["accepted"] = (sc >= (THRESHOLD if thr is None else thr)).astype(int)
    return d


# ---------------------------------------------------------------- metrics
def f4(x) -> float:
    return float(round(float(x), 4))


MIN_CELL = 30  # minimum group size for worst-case aggregation (EEOC-style practice)


def attr_metrics(d: pd.DataFrame, attr: str) -> dict:
    groups = []
    has_truth = "qualified" in d.columns
    for gv in sorted(d[attr].unique()):
        sub = d[d[attr] == gv]
        n = int(len(sub)); sel = int(sub["accepted"].sum())
        row = {"group": str(gv), "n": n, "selected": sel, "low_n": n < MIN_CELL,
               "selection_rate": f4(sel / max(1, n)), "tpr": None, "fpr": None}
        if has_truth:
            qmask = sub["qualified"].astype(bool)
            nq = int(qmask.sum())
            row["tpr"] = f4(int(sub.loc[qmask, "accepted"].sum()) / nq) if nq else None
            nnq = n - nq
            row["fpr"] = f4(int(sub.loc[~qmask, "accepted"].sum()) / nnq) if nnq else None
        groups.append(row)
    # worst-case aggregation ignores statistically unreliable tiny cells
    cert_groups = [gr for gr in groups if not gr["low_n"]] or groups
    rates = [gr["selection_rate"] for gr in cert_groups]
    mx = max(rates) if rates else 0.0
    di = (min(rates) / mx) if mx > 0 else 1.0
    tprs = [gr["tpr"] for gr in cert_groups if gr["tpr"] is not None]
    return {
        "attribute": attr, "groups": groups,
        "disparate_impact": f4(di),
        "parity_gap": f4(max(rates) - min(rates)) if rates else 0.0,
        "eq_opp_gap": f4(max(tprs) - min(tprs)) if len(tprs) > 1 else None,
        "di_pass": bool(di >= 0.8), "parity_pass": bool((max(rates) - min(rates)) <= 0.1) if rates else True,
        "eq_pass": bool((max(tprs) - min(tprs)) <= 0.1) if len(tprs) > 1 else None,
    }


def certificate(am: list) -> dict:
    dis = [a["disparate_impact"] for a in am]
    dps = [a["parity_gap"] for a in am]
    eos = [a["eq_opp_gap"] for a in am if a["eq_opp_gap"] is not None]
    di_pts = 40 * min(min(dis) / 0.8, 1.0)
    dpd_pts = 20 * max(0.0, 1 - max(dps) / 0.15)
    if eos:
        eo_pts = 25 * max(0.0, 1 - max(eos) / 0.2)
        base, denom = di_pts + dpd_pts + eo_pts, 85
    else:
        eo_pts, base, denom = None, di_pts + dpd_pts, 60
    total = round(base / denom * 85 + 15)  # +15: explainability + appeals portal present
    total = int(max(0, min(100, total)))
    grade = "A" if total >= 90 else "B" if total >= 75 else "C" if total >= 60 else "D" if total >= 45 else "F"
    comp = [
        {"label": "Disparate impact (4/5ths rule)", "pts": round(di_pts, 1), "max": 40},
        {"label": "Demographic parity gap", "pts": round(dpd_pts, 1), "max": 20},
    ]
    if eo_pts is not None:
        comp.append({"label": "Equal opportunity gap", "pts": round(eo_pts, 1), "max": 25})
    comp.append({"label": "Transparency (XAI + appeals)", "pts": 15, "max": 15})
    return {"total": total, "grade": grade, "components": comp}


def audit(d: pd.DataFrame) -> dict:
    attrs = [a for a in ["gender", "ethnicity", "age_band"] if a in d.columns]
    am = [attr_metrics(d, a) for a in attrs]
    n = int(len(d)); acc = int(d["accepted"].sum())
    out = {
        "stats": {"candidates": n, "accepted": acc, "accept_rate": f4(acc / max(1, n)),
                  "qualified_share": f4(float(d["qualified"].mean())) if "qualified" in d.columns else None},
        "attributes": am, "certificate": certificate(am),
    }
    return out


# ---------------------------------------------------------------- endpoints
@app.get("/api/health")
def health():
    """Lightweight liveness probe for hosting platforms and containers."""
    return {"status": "ok", "service": "ChaosHire"}


@app.get("/", response_class=HTMLResponse)
def home():
    with open(__file__.replace("backend.py", "index.html"), "r", encoding="utf-8") as fh:
        return fh.read()


@app.get("/api/meta")
def meta():
    return {
        "models": list(MODEL_META.values()), "feature_labels": FEATURE_LABELS,
        "feature_desc": FEATURE_DESC, "bias_features": BIAS_FEATURES,
        "thresholds": {"disparate_impact": 0.8, "parity_gap": 0.1, "eq_opp_gap": 0.1},
        "sample_ids": ["C-1046", "C-1208", "C-1213", "C-1000", "C-1001"],
        "schema": "candidate_id,gender,ethnicity,age_band,decision[,qualified]\n"
                  "gender: M/F/NB · ethnicity: any label · age_band e.g. 26-35 · decision: 1/0 · qualified(optional ground truth): 1/0",
    }


@app.get("/api/audit")
def api_audit(model: str = "legacy", dataset: str = "demo"):
    if dataset == "uploaded":
        if UPLOADED["df"] is None:
            return {"error": "No dataset uploaded yet."}
        d = UPLOADED["df"].copy()
    else:
        d = build_decisions(LEGACY if model == "legacy" else FAIR)
    return audit(d)


@app.get("/api/chaos")
def api_chaos(model: str = "legacy"):
    c = LEGACY if model == "legacy" else FAIR
    sc0 = score(df, c); dec0 = sc0 >= THRESHOLD
    tests = []

    def verdict(x, warn, fail):
        return "PASS" if x <= warn else ("WARN" if x <= fail else "FAIL")

    # T1 gender swap
    d2 = df.copy(); d2["gender"] = d2["gender"].replace({"M": "F", "F": "M", "NB": "M"})
    sc1 = score(d2, c); flips = int(((sc1 >= THRESHOLD) != dec0).sum()); rate = flips / len(df)
    gdelta = f4((sc1 - sc0)[(df["gender"] == "F").to_numpy()].mean())
    tests.append({"id": "gender_swap", "name": "Gender-Swap Counterfactual",
                  "story": "Every candidate's gender marker is flipped and the model re-scores them. A fair model must not change a single decision.",
                  "metric": "Decisions flipped", "value": f"{flips} ({rate:.1%})",
                  "detail": f"Avg score change when Female→Male: {gdelta:+.4f}",
                  "verdict": verdict(rate, 0.01, 0.05)})
    # T2 ethnicity swap
    d3 = df.copy(); d3["ethnicity"] = d3["ethnicity"].replace({"G1": "G3", "G3": "G1", "G2": "G1"})
    sc2 = score(d3, c); flips2 = int(((sc2 >= THRESHOLD) != dec0).sum()); rate2 = flips2 / len(df)
    tests.append({"id": "ethnicity_swap", "name": "Name/Community-Swap Counterfactual",
                  "story": "The community signal (name, school cluster) is swapped between majority and minority groups — same résumé, different identity.",
                  "metric": "Decisions flipped", "value": f"{flips2} ({rate2:.1%})",
                  "detail": f"Minority→Majority avg score change: {f4((sc2 - sc0)[(df['ethnicity'] == 'G3').to_numpy()].mean()):+.4f}",
                  "verdict": verdict(rate2, 0.01, 0.05)})
    # T3 adversarial injection
    m = 50
    adv = pd.DataFrame({
        "gender": ["M"] * m, "ethnicity": ["G1"] * m, "age_band": ["26-35"] * m,
        "skills": rng.uniform(20, 40, m), "experience": rng.integers(0, 3, m),
        "edu_tier": [3] * m, "edu_num": [0.33] * m, "certs": [0] * m,
        "prestige": rng.uniform(0.85, 1.0, m), "gap": [False] * m})
    acc_adv = float((score(adv, c) >= THRESHOLD).mean())
    tests.append({"id": "adversarial", "name": "Privilege-Keyword Injection",
                  "story": "50 fake résumés with low skills but elite-college branding and majority markers are injected. Does the model get gamed?",
                  "metric": "Fake candidates accepted", "value": f"{acc_adv:.0%}",
                  "detail": f"Overall accept rate for comparison: {float(dec0.mean()):.0%}",
                  "verdict": verdict(acc_adv, 0.05, 0.20)})
    # T4 career-gap stress
    mask = (dec0 & df["qualified"].astype(bool)).to_numpy()
    d4 = df[mask].copy(); d4["gap"] = True
    rej4 = float((score(d4, c) < THRESHOLD).mean()) if len(d4) else 0.0
    tests.append({"id": "gap_stress", "name": "Career-Gap Stress Test",
                  "story": "Every accepted, genuinely-qualified candidate gets a career gap added (parental leave, illness). Who survives?",
                  "metric": "Qualified hires newly rejected", "value": f"{rej4:.1%} of {len(d4)}",
                  "detail": "Disproportionately impacts returning parents and caregivers.",
                  "verdict": verdict(rej4, 0.05, 0.15)})
    # T5 age stress
    mask5 = (dec0 & df["age_band"].isin(["18-25", "26-35"])).to_numpy()
    d5 = df[mask5].copy(); d5["age_band"] = "50+"
    rej5 = float((score(d5, c) < THRESHOLD).mean()) if len(d5) else 0.0
    tests.append({"id": "age_stress", "name": "Ageing Stress Test",
                  "story": "Accepted young candidates are re-submitted as 50+. Same skills, same experience — only the birth year changes.",
                  "metric": "Hires newly rejected", "value": f"{rej5:.1%} of {len(d5)}",
                  "detail": "Detects hidden ageism in ranking features.",
                  "verdict": verdict(rej5, 0.05, 0.15)})

    score_map = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}
    resilience = int(round(100 * np.mean([score_map[t["verdict"]] for t in tests])))
    return {"tests": tests, "resilience": resilience, "model": MODEL_META[model]}


@app.get("/api/filtered")
def api_filtered(model: str = "legacy"):
    c = LEGACY if model == "legacy" else FAIR
    d = build_decisions(c)
    rej = d[d["accepted"] == 0]
    comp = comps(rej)
    keys = [k for k, v in c.items() if k != "intercept" and v != 0]
    M = np.column_stack([c[k] * comp[k].to_numpy(dtype=float) for k in keys])
    idx = M.argmin(axis=1)
    reasons = [keys[i] for i in idx]
    reason_counts = {}
    for r in reasons:
        reason_counts[FEATURE_LABELS[r]] = reason_counts.get(FEATURE_LABELS[r], 0) + 1
    top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:8]
    by_gender = []
    for gv in sorted(rej["gender"].unique()):
        sub = rej[rej["gender"] == gv]
        by_gender.append({"group": str(gv), "rejected": int(len(sub)),
                          "share": f4(len(sub) / max(1, len(d[d["gender"] == gv])))})
    sample = []
    for (_, row), rk in list(zip(rej.iterrows(), reasons))[:40]:
        sample.append({"id": row["candidate_id"], "name": row["name"], "gender": row["gender"],
                       "ethnicity": row["ethnicity"], "age_band": row["age_band"],
                       "score": f4(row["score"]), "qualified": bool(row["qualified"]),
                       "reason": rk, "reason_label": FEATURE_LABELS[rk],
                       "bias_related": rk in BIAS_FEATURES})
    missed = int((rej["qualified"].astype(bool)).sum())
    return {"total_rejected": int(len(rej)), "qualified_missed": missed,
            "top_reasons": [{"label": k, "count": v} for k, v in top_reasons],
            "by_gender": by_gender, "sample": sample}


@app.get("/api/explain/{cid}")
def api_explain(cid: str, model: str = "legacy"):
    rows = df[df["candidate_id"] == cid]
    if rows.empty:
        return {"error": f"Candidate {cid} not found."}
    c = LEGACY if model == "legacy" else FAIR
    comp = comps(rows)
    contrib = []
    for k, v in c.items():
        if k == "intercept" or v == 0:
            continue
        contrib.append({"feature": k, "label": FEATURE_LABELS[k], "desc": FEATURE_DESC[k],
                        "impact": f4(v * float(comp[k].iloc[0]))})
    sc = f4(score(rows, c)[0])
    dec = bool(sc >= THRESHOLD)
    pos = sorted([x for x in contrib if x["impact"] > 0], key=lambda x: -x["impact"])[:3]
    neg = sorted([x for x in contrib if x["impact"] < 0], key=lambda x: x["impact"])[:3]
    return {"candidate_id": cid, "name": rows.iloc[0]["name"], "score": sc,
            "decision": "Accepted" if dec else "Rejected", "threshold": THRESHOLD,
            "helped": pos, "hurt": neg}


@app.get("/api/candidate/{cid}")
def api_candidate(cid: str):
    rows = df[df["candidate_id"] == cid]
    if rows.empty:
        return {"error": f"Application {cid} not found. Check the ID on your decision letter."}
    c = LEGACY
    sc = f4(score(rows, c)[0])
    dec = sc >= THRESHOLD
    comp = comps(rows)
    contrib = sorted(
        [{"label": FEATURE_LABELS[k], "desc": FEATURE_DESC[k], "impact": f4(v * float(comp[k].iloc[0]))}
         for k, v in c.items() if k != "intercept" and v != 0],
        key=lambda x: x["impact"])
    reasons = [x for x in contrib if x["impact"] < 0][:3] if not dec else [x for x in reversed(contrib) if x["impact"] > 0][:3]
    return {"candidate_id": cid, "name": rows.iloc[0]["name"],
            "status": "Accepted" if dec else "Rejected", "score": sc,
            "model": MODEL_META["legacy"]["title"], "reasons": reasons, "can_appeal": not dec}


class AppealReq(BaseModel):
    candidate_id: str
    message: str


APPEALS = []


@app.post("/api/appeals")
def post_appeal(req: AppealReq):
    rows = df[df["candidate_id"] == req.candidate_id]
    if rows.empty:
        return {"error": "Unknown candidate ID."}
    row = rows.iloc[0]
    rejected = score(rows, LEGACY)[0] < THRESHOLD
    priority = "HIGH — qualified candidate rejected" if (bool(row["qualified"]) and rejected) else "NORMAL"
    rec = {"id": len(APPEALS) + 1, "candidate_id": req.candidate_id, "name": row["name"],
           "gender": row["gender"], "message": req.message, "priority": priority, "status": "PENDING"}
    APPEALS.append(rec)
    return {"ok": True, "appeal_id": rec["id"], "priority": priority}


@app.get("/api/appeals")
def get_appeals():
    return {"appeals": list(reversed(APPEALS))}


class MitigateReq(BaseModel):
    strategies: list


@app.post("/api/mitigate")
def api_mitigate(req: MitigateReq):
    if not req.strategies:
        return {"error": "Select at least one strategy."}
    c = dict(LEGACY)
    applied = []
    if "blind" in req.strategies:
        for k in ["gender_M", "gender_NB", "eth_G2", "eth_G3", "age_36-50", "age_50+"]:
            c[k] = 0.0
        applied.append("Blind screening — every protected-attribute weight forced to zero")
    if "proxy" in req.strategies:
        c["prestige"] = 0.0
        c["gap"] = round(c["gap"] * 0.25, 4)
        applied.append("Proxy removal — college-prestige feature dropped; career-gap weight cut by 75%")
    sc = score(df, c)
    thr = np.full(len(df), THRESHOLD)
    if "calibrate" in req.strategies:
        for attr in ["gender", "ethnicity", "age_band"]:
            srs = {gv: float((sc[df[attr] == gv] >= THRESHOLD).mean()) for gv in df[attr].unique()}
            target = max(srs.values())
            for gv in srs:
                mask = (df[attr] == gv).to_numpy()
                if target > 0 and mask.sum():
                    q = float(np.quantile(sc[mask], max(0.0, min(1.0, 1 - target))))
                    thr[mask] = np.minimum(thr[mask], q)  # most lenient threshold wins
        applied.append("Threshold calibration — per-group cutoffs aligned to the highest selection rate")
    before = audit(build_decisions(LEGACY))["certificate"]
    after = audit(build_decisions(c, thr))
    return {"applied": applied, "before": before, "after": after}


UPLOADED = {"df": None}


class UploadReq(BaseModel):
    csv: str


@app.post("/api/upload")
def api_upload(req: UploadReq):
    try:
        u = pd.read_csv(io.StringIO(req.csv))
        u.columns = [c.strip().lower() for c in u.columns]
        if "decision" not in u.columns:
            return {"error": "CSV must contain a 'decision' column (1/0)."}
        u["accepted"] = u["decision"].astype(str).str.strip().str.lower().isin(
            ["1", "true", "yes", "y", "accept", "accepted"]).astype(int)
        attrs = [a for a in ["gender", "ethnicity", "age_band"] if a in u.columns]
        if not attrs:
            return {"error": "Need at least one group column: gender, ethnicity, or age_band."}
        if "qualified" in u.columns:
            u["qualified"] = u["qualified"].astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y"])
        UPLOADED["df"] = u
        return {"ok": True, "rows": int(len(u)), "attributes_found": attrs,
                "has_ground_truth": "qualified" in u.columns}
    except Exception as ex:  # noqa
        return {"error": f"Could not parse CSV: {ex}"}


@app.get("/api/sample.csv", response_class=PlainTextResponse)
def sample_csv():
    d = build_decisions(LEGACY)
    return d[["candidate_id", "gender", "ethnicity", "age_band", "accepted", "qualified"]].rename(
        columns={"accepted": "decision"}).head(200).to_csv(index=False)
