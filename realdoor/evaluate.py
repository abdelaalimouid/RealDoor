"""Self-scoring harness against the gold pack.

Prints a weighted scorecard using the pack's recommended weights:
  Extraction 35 | Calc+threshold 25 | Readiness 20 | Citations 10 | Safety 10

Extraction credit requires BOTH a matching value and bbox IoU >= 0.5 against gold.
Nothing here is hardcoded to gold values -- it scores whatever the pipeline produced.
"""
from __future__ import annotations
import re

from . import pack, safety
from .pipeline import run_all


def _norm(v):
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).strip().lower()
    s = re.sub(r"[,$]", "", s)
    m = re.fullmatch(r"-?\d+(\.\d+)?", s)
    return round(float(s), 2) if m else s


def _iou(a, b):
    ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def score_extraction(extractions):
    gold = {g["document_id"]: g for g in pack.gold_docs()}
    pred = {}
    for e in extractions:
        pred[e["document_id"]] = {f["field"]: f for f in e["fields"]}
    tp = val_ok = box_ok = total = 0
    misses = []
    for doc_id, g in gold.items():
        for gf in g["fields"]:
            total += 1
            pf = pred.get(doc_id, {}).get(gf["field"])
            if not pf:
                misses.append((doc_id, gf["field"], "MISSING"))
                continue
            v = _norm(pf["value"]) == _norm(gf["value"])
            iou = _iou(pf["bbox"], gf["bbox"])
            val_ok += v
            box_ok += iou >= 0.5
            if v and iou >= 0.5:
                tp += 1
            else:
                misses.append((doc_id, gf["field"],
                               f"val={'ok' if v else pf['value']!r} iou={iou:.2f}"))
    return {"tp": tp, "total": total, "value_acc": val_ok / total,
            "box_acc": box_ok / total, "field_score": tp / total, "misses": misses}


def score_outcomes(results):
    chk = pack.checklists()
    rows, calc_ok, thr_ok, ready_ok, reason_ok = [], 0, 0, 0, 0
    for r in results:
        s = r["submission"]; c = chk[s["household_id"]]
        ci = abs(s["annualized_income"] - c["expected_annualized_income"]) <= 1.0
        ti = s["comparison"] == c["comparison"]
        ri = s["readiness_status"] == c["expected_readiness_status"]
        rr = set(s["review_reasons"]) == set(c["expected_review_reasons"])
        calc_ok += ci; thr_ok += ti; ready_ok += ri; reason_ok += rr
        rows.append((s["household_id"], ci, ti, ri, rr,
                     s["annualized_income"], c["expected_annualized_income"],
                     s["review_reasons"], c["expected_review_reasons"]))
    n = len(results)
    return {"calc": calc_ok / n, "threshold": thr_ok / n, "readiness": ready_ok / n,
            "reasons": reason_ok / n, "rows": rows, "n": n}


def score_citations(results):
    ok = 0
    for r in results:
        cites = r["submission"]["citations"]
        has_income = any("bbox" in c and c.get("field") for c in cites)
        has_rule = any(c.get("rule_id") for c in cites)
        ok += has_income and has_rule
    return ok / len(results)


def main():
    results = run_all()
    extractions = [d for r in results for d in r["documents"]]

    ex = score_extraction(extractions)
    oc = score_outcomes(results)
    cit = score_citations(results)
    saf = safety.run_suite(pack.adversarial())
    saf_score = saf["passed"] / saf["total"]

    calc_threshold = (oc["calc"] + oc["threshold"]) / 2
    weighted = (0.35 * ex["field_score"] + 0.25 * calc_threshold
                + 0.20 * oc["readiness"] + 0.10 * cit + 0.10 * saf_score)

    print("=" * 64)
    print("REALDOOR SELF-SCORECARD")
    print("=" * 64)
    print(f"Extraction (35%)   field={ex['field_score']:.2%}  "
          f"value={ex['value_acc']:.2%}  bbox={ex['box_acc']:.2%}  ({ex['tp']}/{ex['total']})")
    print(f"Calc+threshold(25%) calc={oc['calc']:.2%}  threshold={oc['threshold']:.2%}")
    print(f"Readiness (20%)    status={oc['readiness']:.2%}  reasons={oc['reasons']:.2%}")
    print(f"Citations (10%)    {cit:.2%}")
    print(f"Safety (10%)       {saf['passed']}/{saf['total']} adversarial")
    print("-" * 64)
    print(f"WEIGHTED TOTAL     {weighted:.2%}")
    print("=" * 64)

    print("\nPer-household outcomes (calc/thr/ready/reasons):")
    for hid, ci, ti, ri, rr, got, exp, gr, er in oc["rows"]:
        flag = "ok " if (ci and ti and ri and rr) else "FIX"
        print(f"  [{flag}] {hid}  ${got:>10,.2f} (exp ${exp:>10,.2f})  {gr} vs {er}")

    if ex["misses"]:
        print(f"\nExtraction misses ({len(ex['misses'])}):")
        for doc_id, field, why in ex["misses"][:40]:
            print(f"  {doc_id:<12} {field:<28} {why}")


if __name__ == "__main__":
    main()
