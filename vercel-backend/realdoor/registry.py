"""Feature registry — 'publish every feature and its purpose' (a non-negotiable requirement).

Every field the system extracts, why it is used, and an explicit statement that no protected
traits, demographic, behavioral, or landlord-revenue features are used.
"""
from __future__ import annotations
from .field_specs import SPECS

PURPOSE = {
    "person_name": "Identify the applicant on their own document (display + confirmation).",
    "household_size": "Select the correct frozen 60% AMI threshold row.",
    "address": "Applicant-provided mailing address (display only; never geocoded to infer traits).",
    "application_date": "Context for document currency.",
    "pay_date": "Establish the pay period for currency checks.",
    "pay_period_start": "Pay-period bound (currency).",
    "pay_period_end": "Pay-period bound (currency).",
    "pay_frequency": "Annualize wages (regular pay x frequency).",
    "regular_hours": "Regular-wage basis for anticipated annual income.",
    "hourly_rate": "Regular-wage basis for anticipated annual income.",
    "gross_pay": "Corroborate the regular basis and detect overtime/variance.",
    "net_pay": "Consistency check only (net <= gross); not used in income.",
    "document_date": "Employment-letter currency (60-day window).",
    "weekly_hours": "Employment-letter corroboration of the wage job.",
    "monthly_benefit": "Benefit income (monthly x 12).",
    "benefit_frequency": "Benefit annualization basis.",
    "statement_month": "Gig statement period.",
    "gross_receipts": "Gig income (monthly x 12), counted but flagged uncorroborated.",
    "platform_fees": "Context only; gross receipts are used, not net.",
    "untrusted_instruction_text": "Captured ONLY to quarantine and display embedded instructions; never executed.",
}

EXCLUDED = [
    "Race, ethnicity, national origin", "Religion", "Disability or health",
    "Immigration status", "Familial status beyond a stated household size",
    "Demographic, behavioral, or landlord-revenue features", "Geocoded/inferred location traits",
]


def registry():
    fields = []
    for dtype, specs in SPECS.items():
        for name in specs:
            if not any(f["field"] == name for f in fields):
                fields.append({"field": name, "document_type": dtype,
                               "purpose": PURPOSE.get(name, "—")})
    return {
        "statement": "RealDoor extracts only the allowlisted fields below and uses them only for "
                     "the stated purpose. It infers no protected traits and makes no eligibility decision.",
        "fields": sorted(fields, key=lambda f: f["field"]),
        "explicitly_not_used": EXCLUDED,
    }
