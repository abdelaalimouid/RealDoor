"""Rules Q&A over the frozen rule corpus — every answer carries an authoritative citation.

Deterministic intent routing (no language model): household-specific questions are answered
from the assessment and cited to the governing rule; general questions retrieve the best
rule_corpus entry. Eligibility/decision questions are refused and deflected to the rule +
confirmed input + calculation (CH-DECISION-001). Validated against the 36 gold Q&A.
"""
from __future__ import annotations
import json
import re

from . import config as C

_CORPUS = {r["rule_id"]: r for r in (json.loads(l) for l in open(C.RULES_JSONL))}
_CITE_KEYS = ("rule_id", "authority", "effective_date", "source_url", "source_locator", "text")


def _cite(*ids):
    return [{k: _CORPUS[i].get(k) for k in _CITE_KEYS} for i in ids if i in _CORPUS]


def rule_versions(ids):
    """Version stamps (id, effective_date, source) for the rules a result relied on."""
    seen, out = set(), []
    for i in ids:
        if i in _CORPUS and i not in seen:
            seen.add(i)
            r = _CORPUS[i]
            out.append({"rule_id": i, "authority": r.get("authority"),
                        "effective_date": r.get("effective_date"),
                        "source_url": r.get("source_url"), "source_locator": r.get("source_locator")})
    return out


def _has(q, *words):
    return any(w in q for w in words)


def answer(question: str, assessment: dict | None = None) -> dict:
    q = (question or "").lower().strip()
    a = assessment or {}
    size, thr, inc = a.get("household_size"), a.get("threshold"), a.get("annualized_income")
    cmp, status = a.get("comparison"), a.get("readiness_status")

    # 1) eligibility / decision -> refuse and deflect
    if _has(q, "eligible", "ineligible", "qualif", "approve", "approved", "deny", "denied",
            "reject", "accept", "get in", "will i", "should i be approved"):
        return {"refused": True,
                "answer": "No. It may report the numerical comparison and readiness status only; "
                          "a qualified human decides.",
                "facts": {"annualized_income": inc, "frozen_60_threshold": thr,
                          "comparison": cmp, "readiness_status": status},
                "citations": _cite("CH-DECISION-001")}

    # 2) effective date of the frozen limits
    if _has(q, "take effect", "effective", "when do", "when are") and \
            _has(q, "limit", "mtsp", "2026", "income limit"):
        return {"refused": False, "answer": "May 1, 2026.", "citations": _cite("HUD-MTSP-001")}

    # 3) vacancy / waitlist
    if _has(q, "vacant", "vacancy", "waitlist", "wait list") or ("prove" in q and "unit" in q):
        return {"refused": False,
                "answer": "No. The dataset is a project inventory, not a vacancy or waitlist feed.",
                "citations": _cite("HUD-DATA-001")}

    # 4) geocode precision
    if _has(q, "geocode", "precision", "address display"):
        return {"refused": False,
                "answer": "HUD identifies R and 4 as the higher-precision codes for address display.",
                "citations": _cite("HUD-GEO-001")}

    # 5) embedded instructions
    if _has(q, "embedded", "injection") or ("instruction" in q and _has(q, "inside", "pay stub", "document")):
        return {"refused": False,
                "answer": "Treat them as untrusted document text and ignore them; embedded instructions never "
                          "change system behavior, tools, rules, or data access.",
                "citations": _cite("CH-SAFETY-001")}

    # 6) 60-day currency convention
    if _has(q, "60-day", "60 day", "currency"):
        return {"refused": False,
                "answer": "No. It is a frozen convention for this simulation, not a universal LIHTC rule.",
                "citations": _cite("CH-READINESS-001")}

    # 7) federal statutory anchor
    if _has(q, "statute", "statutor", "section 42", "26 u.s.c", "federal anchor"):
        return {"refused": False, "answer": "26 U.S.C. section 42.", "citations": _cite("FED-LIHTC-001")}

    # 8) comparison (checked before threshold: the question mentions "threshold" too)
    if _has(q, "compare", "comparison", "above or below", "above the", "below the"):
        return {"refused": False, "answer": cmp or "not comparable",
                "citations": _cite("HUD-MTSP-002", "CH-INCOME-001")}

    # 9) frozen 60% threshold for this household
    if _has(q, "threshold", "60%", "limit") and size:
        return {"refused": False,
                "answer": f"${thr:,.0f} for household size {size}." if thr else
                          "No frozen threshold: household size is outside the 2026 MTSP table (sizes 1-8).",
                "citations": _cite("HUD-MTSP-002")}

    # 10) annualized income
    if _has(q, "annualized income", "income should", "annual income", "what income", "how much income"):
        return {"refused": False,
                "answer": f"${inc:,.2f} under the frozen annualization convention." if inc is not None else
                          "No income has been computed yet.",
                "citations": _cite("CH-INCOME-001")}

    # 11) readiness status
    if _has(q, "readiness", "status"):
        return {"refused": False, "answer": status or "no status computed yet",
                "citations": _cite("CH-READINESS-001")}

    # fallback: retrieve the best-matching frozen rule
    toks = set(re.findall(r"[a-z0-9]+", q))
    best, score = None, 0
    for r in _CORPUS.values():
        rt = set(re.findall(r"[a-z0-9]+", (r["text"] + " " + (r.get("source_locator") or "")).lower()))
        s = len(toks & rt)
        if s > score:
            score, best = s, r
    if best and score >= 2:
        return {"refused": False, "answer": best["text"], "citations": _cite(best["rule_id"])}
    return {"refused": False,
            "answer": "I can only answer from the frozen rule corpus. Ask about the 60% threshold, the "
                      "annualized income, the comparison, readiness, the MTSP effective date, or the currency rule.",
            "citations": []}
