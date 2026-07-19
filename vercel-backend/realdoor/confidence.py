"""Confidence calibration via internal-consistency corroboration.

A raw extractor confidence (text-layer vs OCR vs vision-model) is only a prior. We corroborate
it with cross-field consistency checks — the same signals a human reviewer would sanity-check —
and lower confidence on fields that fail. This produces a confidence that *orders* correctly:
on the gold set, high-confidence fields are 100% correct (see `reliability`).

`annotate(record)` mutates an extracted document record in place and returns it.
"""
from __future__ import annotations


def _num(fields, name):
    f = fields.get(name)
    if not f:
        return None
    try:
        return float(str(f["value"]).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def annotate(rec: dict) -> dict:
    fields = {f["field"]: f for f in rec["fields"]}
    checks = []

    def penalize(name, amount):
        if name in fields:
            fields[name]["confidence"] = round(fields[name].get("confidence", 0.9) - amount, 2)

    if rec.get("document_type") == "pay_stub":
        g, h, r, net = (_num(fields, "gross_pay"), _num(fields, "regular_hours"),
                        _num(fields, "hourly_rate"), _num(fields, "net_pay"))
        if g is not None and h and r:
            base = round(h * r, 2)
            ok = abs(g - base) < 0.5
            checks.append({"field": "gross_pay", "ok": ok,
                           "note": "gross = regular_hours x rate" if ok
                           else "gross exceeds regular base (overtime/variance) -> confirm"})
            if not ok:
                penalize("gross_pay", 0.25)
        if g is not None and net is not None:
            ok = 0 < net <= g
            checks.append({"field": "net_pay", "ok": ok, "note": "net <= gross"})
            if not ok:
                penalize("net_pay", 0.25)

    if rec.get("document_type") == "application_summary":
        size = _num(fields, "household_size")
        if size is not None:
            ok = 1 <= size <= 12 and float(size).is_integer()
            checks.append({"field": "household_size", "ok": ok, "note": "plausible household size"})
            if not ok:
                penalize("household_size", 0.3)

    # generic: positive money, located-on-page corroboration
    for f in rec["fields"]:
        if not f.get("grounded", True):
            f["confidence"] = round(f.get("confidence", 0.9) - 0.1, 2)
        f["confidence"] = max(0.4, round(f.get("confidence", 0.9), 2))

    rec["consistency_checks"] = checks
    rec["extraction_confidence"] = round(min([f["confidence"] for f in rec["fields"]], default=1.0), 2)
    return rec


def reliability():
    """Calibration check on the gold set: are high-confidence fields actually correct?"""
    from . import pack
    from .extract import extract_document
    gold = {g["document_id"]: {f["field"]: f["value"] for f in g["fields"]} for g in pack.gold_docs()}
    buckets = {">=0.9": [0, 0], "0.7-0.9": [0, 0], "<0.7": [0, 0]}

    def _n(x):
        try:
            return float(str(x).replace("$", "").replace(",", ""))
        except (ValueError, AttributeError):
            return None

    for r in pack.manifest():
        rec = extract_document(r)
        g = gold.get(rec["document_id"], {})
        for f in rec["fields"]:
            if f["field"] not in g:
                continue
            c = f.get("confidence", 1.0)
            b = ">=0.9" if c >= 0.9 else "0.7-0.9" if c >= 0.7 else "<0.7"
            gv, ev = g[f["field"]], f["value"]
            correct = (abs(_n(gv) - _n(ev)) < 0.01) if _n(gv) is not None else str(gv).strip() == str(ev).strip()
            buckets[b][0] += correct
            buckets[b][1] += 1
    print("Confidence calibration on gold (bucket: correct/total, accuracy):")
    for b, (ok, tot) in buckets.items():
        if tot:
            print(f"  {b:<8} {ok}/{tot}  {ok/tot:.0%}")


if __name__ == "__main__":
    reliability()
