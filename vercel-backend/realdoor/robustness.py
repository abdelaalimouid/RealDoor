"""Property-based generalization harness.

The hidden challenge test perturbs names and values while keeping the layout/schema.
100% on the 6 seed households proves nothing about that. Here we synthesize thousands
of randomized households -- new names, addresses, wages, frequencies, structures -- feed
them through the *same* readiness engine, and check its output against an INDEPENDENT
oracle (a plain re-summation of the values we planted). If the engine had memorized the
seed numbers, this would collapse.

Run:  python -m realdoor.robustness  [N]  [seed]
"""
from __future__ import annotations
import random
import sys

from . import pack
from .calc import annualize, FREQUENCY
from .readiness import assess

FREQS = list(FREQUENCY)
NAMES = ["Mara North", "Jonas Vale", "Avery Moss", "Rin Calder", "Sam Okoro",
         "Lena Park", "Diego Ruiz", "Nia Bello", "Omar Haddad", "Tess Lindqvist"]
STREETS = ["14 Lantern Way", "9 Paper Mill Road", "3 Juniper Court", "77 Glass Street",
           "22 Meadow Signal Ave", "5 Atlas Row", "101 Cedar Loop", "8 Harbor Bend"]
EVENT = "2026-07-18"


EMPLOYERS = ["Harbor Kite Market", "Copper Finch Services", "Blue Acorn Foods",
             "Moonrise Repair Co.", "North Loop Books", "Cobalt Window Works",
             "Ridge Line Bakery", "Union Freight Ltd", "Pine State Clinic"]


def _f(field, value):
    return {"field": field, "value": value, "page": 1, "bbox": [0, 0, 10, 10],
            "bbox_units": "pdf_points_bottom_left_origin"}


def _doc(did, hid, dtype, fields, employer=None):
    return {"document_id": did, "household_id": hid, "document_type": dtype,
            "page_count": 1, "page_size_points": [612, 792], "employer": employer,
            "fields": [_f(k, v) for k, v in fields.items()]}


def _ocr_noise(name, rng):
    """Mimic OCR error by perturbing 1-2 characters across the employer name."""
    toks = name.split()
    for _ in range(rng.choice([1, 2])):
        i = rng.randrange(len(toks))
        t = toks[i]
        if len(t) > 2:
            j = rng.randrange(1, len(t) - 1)
            toks[i] = t[:j] + rng.choice("aeioulrnm") + t[j + 1:]
    return " ".join(toks)


def make_case(rng: random.Random):
    hid = f"SYN-{rng.randint(0, 999999):06d}"
    size = rng.choices(list(range(1, 9)) + [9, 10], weights=[10]*8 + [1, 1])[0]
    name = rng.choice(NAMES)
    docs = [_doc(f"{hid}-D01", hid, "application_summary",
                 {"person_name": name, "household_size": size,
                  "address": rng.choice(STREETS) + ", MA 02118", "application_date": "2026-07-10"})]

    oracle_income = 0.0
    reasons = set()

    # 1-3 distinct wage jobs, each a distinct employer. Rates may COLLIDE across
    # employers (the case the old rate-grouping merged incorrectly -> must still sum).
    njobs = rng.choices([1, 2, 3], weights=[7, 2, 1])[0]
    employers = rng.sample(EMPLOYERS, njobs)
    rate_pool = [12.0, 18.5, 22.0, 24.0, 28.5, 33.0, 45.0, 52.0, 60.0]
    for j, emp in enumerate(employers):
        rate = rng.choice(rate_pool)            # collisions allowed on purpose
        hours = float(rng.choice([20, 32, 38, 40, 60, 64, 68, 76, 80]))
        freq = rng.choice(FREQS)
        base = round(hours * rate, 2)
        oracle_income += annualize(base, freq)
        overtime = rng.random() < 0.25
        nstubs = rng.choice([1, 2])
        for s in range(nstubs):
            gross = base + (round(rng.uniform(100, 600), 2) if (overtime and s == 0) else 0.0)
            # occasionally noise the employer on the 2nd stub (OCR) -- must still cluster
            emp_seen = _ocr_noise(emp, rng) if (s == 1 and rng.random() < 0.4) else emp
            docs.append(_doc(f"{hid}-W{j}{s}", hid, "pay_stub",
                             {"person_name": name, "pay_date": "2026-06-27",
                              "pay_period_start": "2026-06-10", "pay_period_end": "2026-06-23",
                              "pay_frequency": freq, "regular_hours": hours,
                              "hourly_rate": rate, "gross_pay": gross,
                              "net_pay": round(gross * 0.78, 2)},
                             employer=emp_seen))
        if overtime:
            reasons.add("PAY_STUB_TOTAL_CONFLICT")

    # optional benefit
    if rng.random() < 0.5:
        monthly = round(rng.uniform(200, 1500), 2)
        oracle_income += annualize(monthly, "monthly")
        docs.append(_doc(f"{hid}-B", hid, "benefit_letter",
                         {"person_name": name, "document_date": "2026-06-13",
                          "monthly_benefit": monthly, "benefit_frequency": "monthly"}))

    # optional gig (counted, flagged)
    if rng.random() < 0.35:
        receipts = round(rng.uniform(200, 2000), 2)
        oracle_income += annualize(receipts, "monthly")
        docs.append(_doc(f"{hid}-G", hid, "gig_statement",
                         {"person_name": name, "statement_month": "2026-06",
                          "gross_receipts": receipts, "platform_fees": 120.0}))
        reasons.add("GIG_INCOME_UNCORROBORATED")

    # optional employment letter (sometimes expired: before 2026-05-19)
    if rng.random() < 0.5:
        d = rng.choice(["2026-07-06", "2026-06-01", "2026-04-14", "2026-02-02", "2026-05-20"])
        docs.append(_doc(f"{hid}-E", hid, "employment_letter",
                         {"person_name": name, "document_date": d,
                          "weekly_hours": 38.0, "hourly_rate": 24.0}))
        if d < "2026-05-19":
            reasons.add("EMPLOYMENT_LETTER_EXPIRED")

    if size > 8:
        reasons.add("NO_FROZEN_THRESHOLD")
    if oracle_income == 0.0:
        reasons.add("MISSING_INCOME_EVIDENCE")

    oracle_income = round(oracle_income, 2)
    row = pack.threshold_for(size)
    if row:
        comparison = "below_or_equal" if oracle_income <= row["threshold_60"] else "above"
    else:
        comparison = "no_frozen_threshold"
    status = "READY_TO_REVIEW" if not reasons else "NEEDS_REVIEW"
    oracle = {"income": oracle_income, "comparison": comparison,
              "status": status, "reasons": reasons}
    return hid, docs, oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    rng = random.Random(seed)
    fails = []
    checks = {"income": 0, "comparison": 0, "status": 0, "reasons": 0}
    for _ in range(n):
        hid, docs, o = make_case(rng)
        a = assess(hid, docs)
        ok_income = abs(a["annualized_income"] - o["income"]) <= 1.0
        ok_cmp = a["comparison"] == o["comparison"]
        ok_status = a["readiness_status"] == o["status"]
        ok_reasons = set(a["review_reasons"]) == o["reasons"]
        checks["income"] += ok_income
        checks["comparison"] += ok_cmp
        checks["status"] += ok_status
        checks["reasons"] += ok_reasons
        if not (ok_income and ok_cmp and ok_status and ok_reasons):
            fails.append((hid, o, {"income": a["annualized_income"],
                                   "comparison": a["comparison"],
                                   "status": a["readiness_status"],
                                   "reasons": a["review_reasons"]}))

    print("=" * 60)
    print(f"ROBUSTNESS: {n} randomized households (seed={seed})")
    print("=" * 60)
    for k, v in checks.items():
        print(f"  {k:<12} {v}/{n}  {v/n:.2%}")
    print(f"  {'ALL-PASS':<12} {n-len(fails)}/{n}  {(n-len(fails))/n:.2%}")
    if fails:
        print(f"\nFirst failures ({len(fails)} total):")
        for hid, o, got in fails[:8]:
            print(f"  {hid}\n     oracle={o}\n     got   ={got}")


if __name__ == "__main__":
    main()
