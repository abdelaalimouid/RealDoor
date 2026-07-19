"""End-to-end: manifest -> extraction -> readiness -> submission records."""
from __future__ import annotations
import json

from . import config as C
from . import pack
from .extract import extract_document
from .readiness import assess


def run_household(household_id: str) -> dict:
    docs = [extract_document(row) for row in pack.manifest_for(household_id)]
    a = assess(household_id, docs)
    submission = {
        "household_id": household_id,
        "annualized_income": a["annualized_income"],
        "comparison": a["comparison"],
        "readiness_status": a["readiness_status"],
        "review_reasons": a["review_reasons"],
        "citations": a["citations"],
        "decision_boundary": a["decision_boundary"],
    }
    return {"submission": submission, "assessment": a, "documents": docs}


def run_all() -> list:
    return [run_household(h) for h in pack.household_ids()]


def main():
    out_dir = C.PACK.parent.parent / "realdoor" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = run_all()
    with open(out_dir / "submission.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r["submission"]) + "\n")
    with open(out_dir / "extractions.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            for d in r["documents"]:
                f.write(json.dumps(d) + "\n")
    for r in results:
        s = r["submission"]
        print(f"{s['household_id']}: ${s['annualized_income']:>10,.2f}  {s['comparison']:<14} "
              f"{s['readiness_status']:<14} {s['review_reasons']}")
    print(f"\nWrote {out_dir/'submission.jsonl'} and extractions.jsonl")


if __name__ == "__main__":
    main()
