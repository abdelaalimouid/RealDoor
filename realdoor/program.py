"""The active housing program as configuration.

Adding a new metro or program is a config entry (limits table + rule corpus + required-doc
rule), not a code change — this is how RealDoor would multi-tenant across RealPage's markets.
Values here are frozen to the challenge scenario.
"""
from __future__ import annotations
from . import config as C

ACTIVE = {
    "program_id": "lihtc-boston-cambridge-quincy-fy2026",
    "program": "LIHTC — Low-Income Housing Tax Credit",
    "metro": "Boston-Cambridge-Quincy, MA-NH HMFA (CBSA 14460)",
    "rule_year": "FY2026",
    "threshold_basis": "60% AMI (HUD MTSP limits)",
    "effective_date": "2026-05-01",
    "currency_window_days": C.CURRENCY_WINDOW_DAYS,
    "required_documents": ["application_summary", "pay_stub", "employment_letter"],
    "conditional_documents": {
        "benefit_letter": "required when benefit income is present",
        "gig_income_corroboration": "required when a gig statement is present",
    },
    "sources": {
        "income_limits": "HUD MTSP FY2026 (HUD-MTSP-002) — huduser.gov/portal/datasets/mtsp.html",
        "income_method": "HUD Handbook 4350.3, Part 5 (anticipated annual income)",
        "statute": "26 U.S.C. §42",
    },
    "extensibility_note": "A new program/metro is added as a config bundle: MTSP limits table, "
                          "rule corpus, currency window, and required-document rule.",
}


def active():
    return ACTIVE
