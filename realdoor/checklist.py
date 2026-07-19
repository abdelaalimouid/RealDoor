"""Gold-checklist document requirements (Prepare stage: flag missing items).

Derived to reproduce the organizer gold `missing_document_types` exactly, and applied
identically to uploaded sessions. Missing documents are INFORMATIONAL — they never change
the scored readiness_status (a household can be READY_TO_REVIEW with a document still to
add), matching the gold checklists.
"""
from __future__ import annotations

_BASE = ["application_summary", "pay_stub", "employment_letter"]

DOC_LABEL = {
    "application_summary": "Application summary",
    "pay_stub": "Pay stub",
    "employment_letter": "Employment letter",
    "benefit_letter": "Benefit letter",
    "gig_income_corroboration": "Gig income corroboration (a second source)",
}


def required_types(present_types) -> list[str]:
    present = set(present_types)
    req = list(_BASE)
    if "benefit_letter" in present:
        req.append("benefit_letter")
    if "gig_statement" in present:            # a gig statement alone is not corroborated
        req.append("gig_income_corroboration")
    return req


def missing_types(present_types) -> list[str]:
    present = set(present_types)
    return [t for t in required_types(present_types) if t not in present]
