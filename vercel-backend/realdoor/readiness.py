"""Rule-grounded readiness engine.

Turns a household's extracted documents into:
  annualized_income, comparison, readiness_status, review_reasons, citations.

Reason taxonomy (from evaluation/application_checklists.json):
  PAY_STUB_TOTAL_CONFLICT | GIG_INCOME_UNCORROBORATED | EMPLOYMENT_LETTER_EXPIRED
  MISSING_INCOME_EVIDENCE (defensive; not present in the 6 seed households)

READY_TO_REVIEW only when required income evidence is present, current under the
60-day convention, internally consistent, and traceable. Never an eligibility call.
"""
from __future__ import annotations
import re
from difflib import SequenceMatcher
from datetime import date

from . import config as C
from . import pack
from . import checklist
from .calc import annualize, compare_to_threshold

_CONFLICT_TOL = 100.0  # dollars of annualized difference tolerated between pay stubs


def _field(doc, name):
    for f in doc["fields"]:
        if f["field"] == name:
            return f
    return None


def _val(doc, name):
    f = _field(doc, name)
    return f["value"] if f else None


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


_EMP_SIM_THRESHOLD = 0.72


def _emp_tokens(name):
    return set(t for t in re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split() if t)


def _emp_sim(a, b):
    """Employer-name similarity tolerant of OCR noise. Combines character-level
    similarity (catches typos like 'Kite'->'Klte') with token Jaccard (catches
    dropped/reordered words); genuinely different names score low on both."""
    na = re.sub(r"[^a-z0-9]", "", (a or "").lower())
    nb = re.sub(r"[^a-z0-9]", "", (b or "").lower())
    if not na or not nb:
        return 0.0
    char = SequenceMatcher(None, na, nb).ratio()
    ta, tb = _emp_tokens(a), _emp_tokens(b)
    tok = len(ta & tb) / len(ta | tb) if (ta and tb) else 0.0
    return max(char, tok)


def _same_job(s1, s2):
    """Two stubs belong to one job if their employers match (fuzzily); when an
    employer is missing, fall back to an identical wage signature. Clearly
    different employers are NEVER merged, so independent sources are summed."""
    e1, e2 = s1.get("employer"), s2.get("employer")
    if e1 and e2:
        return _emp_sim(e1, e2) >= _EMP_SIM_THRESHOLD
    return (s1["rate"] == s2["rate"] and s1["hours"] == s2["hours"]
            and s1["freq"] == s2["freq"])


def _cluster_jobs(stubs):
    """Union-find grouping of pay stubs into distinct jobs (income sources)."""
    n = len(stubs)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _same_job(stubs[i], stubs[j]):
                parent[find(i)] = find(j)
    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(stubs[i])
    return list(clusters.values())


def _cite(doc, name, rule_id):
    f = _field(doc, name)
    if not f:
        return None
    return {"document_id": doc["document_id"], "page": f["page"],
            "bbox": f["bbox"], "field": name, "rule_id": rule_id}


def _parse_date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _expired(d: date | None) -> bool:
    if d is None:
        return False
    return (C.EVENT_DATE - d).days > C.CURRENCY_WINDOW_DAYS


def assess(household_id: str, docs: list) -> dict:
    by_type = {}
    for d in docs:
        by_type.setdefault(d["document_type"], []).append(d)

    reasons, citations, ledger = [], [], []

    # --- household size ---
    size = None
    for d in by_type.get("application_summary", []):
        size = _val(d, "household_size") or size

    # === WAGE INCOME (HUD 4350.3 anticipated-annual basis) ============================
    # Anticipated recurring wage is REGULAR pay (regular_hours x hourly_rate), NOT the
    # printed gross, which may include non-recurring overtime. Overtime/variable pay
    # cannot be reliably annualized from a single period, so a stub whose gross exceeds
    # its regular base -- or two stubs for one job that disagree -- is flagged for human
    # review rather than silently averaged. Distinct jobs (different pay rate) are summed
    # as "independently documented recurring sources" (CH-INCOME-001).
    stubs = []
    for d in by_type.get("pay_stub", []):
        freq = _val(d, "pay_frequency")
        rate = _num(_val(d, "hourly_rate"))
        hours = _num(_val(d, "regular_hours"))
        gross = _num(_val(d, "gross_pay"))
        if not freq:
            continue
        base = round(hours * rate, 2) if (hours and rate) else gross
        if base is None:
            continue
        stubs.append({"doc": d, "employer": d.get("employer"), "freq": freq,
                      "rate": rate, "hours": hours, "base": base, "gross": gross})

    wage = 0.0
    for cluster in _cluster_jobs(stubs):
        rep = cluster[0]
        bases = [s["base"] for s in cluster if s["base"] is not None]
        grosses = [s["gross"] for s in cluster if s["gross"] is not None]
        anticipated = annualize(min(bases) if bases else rep["base"], rep["freq"])
        wage += anticipated
        # conflict: grosses disagree, or a gross exceeds its regular base (overtime/variance)
        conflict = (len({round(g) for g in grosses}) > 1) or any(
            s["base"] is not None and s["gross"] is not None
            and round(s["gross"]) != round(s["base"]) for s in cluster)
        if conflict:
            reasons.append("PAY_STUB_TOTAL_CONFLICT")
            citations.append(_cite(rep["doc"], "gross_pay", C.READINESS_RULE_ID))
        citations.append(_cite(rep["doc"], "gross_pay", C.INCOME_RULE_ID))
        ledger.append({"step": "wage", "employer": rep.get("employer"),
                       "stubs": len(cluster),
                       "regular_basis": min(bases) if bases else rep["base"],
                       "frequency": rep["freq"], "annualized": anticipated,
                       "conflict": conflict})

    # === BENEFIT INCOME (independent recurring source) ================================
    benefit = 0.0
    for d in by_type.get("benefit_letter", []):
        amt = _num(_val(d, "monthly_benefit"))
        freq = _val(d, "benefit_frequency") or "monthly"
        if amt is None:
            continue
        b = annualize(amt, freq)
        benefit += b
        citations.append(_cite(d, "monthly_benefit", C.INCOME_RULE_ID))
        ledger.append({"step": "benefit", "monthly": amt, "frequency": freq, "annualized": b})

    # === GIG INCOME (counted, but flagged as uncorroborated) =========================
    gig = 0.0
    for d in by_type.get("gig_statement", []):
        receipts = _num(_val(d, "gross_receipts"))
        if receipts is None:
            continue
        g = annualize(receipts, "monthly")   # gig statements are monthly (statement_month)
        gig += g
        citations.append(_cite(d, "gross_receipts", C.INCOME_RULE_ID))
        reasons.append("GIG_INCOME_UNCORROBORATED")
        ledger.append({"step": "gig", "monthly_receipts": receipts, "annualized": g,
                       "corroborated": False})

    # === CURRENCY: employment letter within the 60-day window ========================
    for d in by_type.get("employment_letter", []):
        if _expired(_parse_date(_val(d, "document_date"))):
            reasons.append("EMPLOYMENT_LETTER_EXPIRED")
            citations.append(_cite(d, "document_date", C.READINESS_RULE_ID))
            ledger.append({"step": "currency", "document": d["document_id"],
                           "date": _val(d, "document_date"), "current": False})

    if not stubs and benefit == 0.0 and gig == 0.0:
        reasons.append("MISSING_INCOME_EVIDENCE")

    annualized = round(wage + benefit + gig, 2)

    # --- threshold comparison (deterministic; not a decision) ---
    row = pack.threshold_for(size) if size else None
    if row:
        threshold = row["threshold_60"]
        comparison = compare_to_threshold(annualized, threshold)
        citations.append({"rule_id": C.THRESHOLD_RULE_ID,
                          "source_url": row["source_url"],
                          "source_page": row["source_page"],
                          "household_size": size, "threshold": threshold})
        ledger.append({"step": "threshold", "household_size": size,
                       "threshold_60": threshold, "annualized": annualized,
                       "comparison": comparison})
    else:
        threshold, comparison = None, "no_frozen_threshold"
        # Frozen MTSP table only covers sizes 1-8; anything else has no frozen threshold.
        reasons.append("NO_FROZEN_THRESHOLD")
        ledger.append({"step": "threshold", "household_size": size,
                       "note": "outside frozen MTSP table (sizes 1-8)"})

    status = "READY_TO_REVIEW" if not reasons else "NEEDS_REVIEW"
    ledger.append({"step": "readiness", "status": status, "reasons": sorted(set(reasons))})

    # Informational document checklist (never changes readiness_status; matches gold).
    present_types = sorted({d["document_type"] for d in docs})
    missing_docs = checklist.missing_types(present_types)

    return {
        "household_id": household_id,
        "household_size": size,
        "annualized_income": annualized,
        "income_breakdown": {"wages": round(wage, 2), "benefits": round(benefit, 2),
                             "gig": round(gig, 2)},
        "threshold": threshold,
        "comparison": comparison,
        "readiness_status": status,
        "review_reasons": sorted(set(reasons)),
        "documents_present": present_types,
        "documents_needed": missing_docs,
        "citations": [c for c in citations if c],
        "reasoning_ledger": ledger,
        "decision_boundary": "No eligibility, approval, denial, or priority is asserted (CH-DECISION-001).",
    }
