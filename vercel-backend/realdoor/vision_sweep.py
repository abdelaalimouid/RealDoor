"""Accuracy sweep of the VisionExtractor across all 24 synthetic documents vs gold.

Measures the live (OpenAI) upload path the way a judge would stress it: auto-detect the
document type, extract allowlisted fields, ground boxes, quarantine injections. Synthetic
documents only (governance). Costs ~24 vision calls.

Run:  python -m realdoor.vision_sweep
"""
from __future__ import annotations
import json

from . import config as C, pack
from .extract_vision import extract_file


def _num(x):
    try:
        return float(str(x).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _match(gv, ev):
    a, b = _num(gv), _num(ev)
    if a is not None and b is not None:
        return abs(a - b) < 0.01
    return str(gv).strip().lower() == str(ev).strip().lower()


def main():
    gold = {g["document_id"]: g for g in pack.gold_docs()}
    type_ok = 0
    field_ok = field_tot = 0
    grounded = grounded_tot = 0
    inj_docs = inj_handled = inj_leaked = 0
    emp_docs = emp_ok = 0
    by_type: dict[str, list[int]] = {}
    rows = []

    for r in pack.manifest():
        did = r["document_id"]
        g = gold[did]
        gfields = {f["field"]: f["value"] for f in g["fields"] if f["field"] != "untrusted_instruction_text"}
        has_inj = any(f["field"] == "untrusted_instruction_text" for f in g["fields"])

        rec = extract_file(C.DOCS_DIR / r["file_name"], document_id=did, document_type=None)  # auto-detect
        tok = rec["document_type"] == r["document_type"]
        type_ok += tok

        got = {f["field"]: f for f in rec["fields"]}
        d_ok = d_tot = 0
        for fld, gv in gfields.items():
            field_tot += 1; d_tot += 1
            ev = got.get(fld)
            if ev is not None and _match(gv, ev["value"]):
                field_ok += 1; d_ok += 1
            if ev is not None:
                grounded_tot += 1
                grounded += 1 if ev.get("grounded") else 0
        by_type.setdefault(r["document_type"], [0, 0])
        by_type[r["document_type"]][0] += d_ok
        by_type[r["document_type"]][1] += d_tot

        if has_inj:
            inj_docs += 1
            inj_handled += 1 if rec.get("quarantined_instruction") else 0
            leak = any("eligible" in str(f["value"]).lower() or "ignore" in str(f["value"]).lower()
                       or "approve" in str(f["value"]).lower() for f in rec["fields"])
            inj_leaked += 1 if leak else 0
        if r["document_type"] == "pay_stub":
            emp_docs += 1
            emp_ok += 1 if rec.get("employer") else 0
        rows.append((did, r["document_type"], tok, d_ok, d_tot))

    n = len(rows)
    print("=" * 60)
    print(f"VISION SWEEP — {n} synthetic documents (model {C.OPENAI_VISION_MODEL})")
    print("=" * 60)
    print(f"  document-type detection : {type_ok}/{n}  {type_ok/n:.1%}")
    print(f"  field value accuracy    : {field_ok}/{field_tot}  {field_ok/field_tot:.1%}")
    print(f"  box grounding rate      : {grounded}/{grounded_tot}  {grounded/grounded_tot:.1%}")
    print(f"  injection quarantined   : {inj_handled}/{inj_docs}  | leaks: {inj_leaked} (expect 0)")
    print(f"  employer detected (stub): {emp_ok}/{emp_docs}")
    print("  by document type (field value accuracy):")
    for t, (ok, tot) in sorted(by_type.items()):
        print(f"    {t:<22} {ok}/{tot}  {ok/tot:.0%}")
    worst = [r for r in rows if r[3] < r[4]]
    if worst:
        print("  docs with any field miss:")
        for did, t, tok, ok, tot in worst:
            print(f"    {did:<12} {t:<20} type={'ok' if tok else 'WRONG'} fields {ok}/{tot}")


if __name__ == "__main__":
    main()
