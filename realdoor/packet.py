"""Human-readable readiness packet (PDF) -- the work product a caseworker actually uses.

Not an eligibility determination: it presents evidence, deterministic calculations,
citations, and open review items for a qualified human to decide on.
"""
from __future__ import annotations
from datetime import datetime

from fpdf import FPDF

from . import config as C

NAVY = (30, 58, 95)
INK = (20, 24, 31)
SOFT = (90, 100, 112)
AMBER = (154, 91, 10)
LINE = (200, 200, 190)

REASON_LABELS = {
    "PAY_STUB_TOTAL_CONFLICT": "Pay stubs for one job disagree (possible overtime); confirm the recurring amount.",
    "GIG_INCOME_UNCORROBORATED": "Gig income is self-reported and not corroborated by a second source.",
    "EMPLOYMENT_LETTER_EXPIRED": "Employment letter is older than the 60-day currency window.",
    "MISSING_INCOME_EVIDENCE": "No income evidence was provided.",
    "NO_FROZEN_THRESHOLD": "Household size falls outside the frozen 2026 MTSP table (sizes 1-8).",
}
FIELD_LABEL = {
    "person_name": "Name", "household_size": "Household size", "address": "Address",
    "pay_frequency": "Pay frequency", "regular_hours": "Regular hours", "hourly_rate": "Hourly rate",
    "gross_pay": "Gross pay", "net_pay": "Net pay", "monthly_benefit": "Monthly benefit",
    "gross_receipts": "Gross receipts", "document_date": "Letter date", "weekly_hours": "Weekly hours",
}


def _money(n):
    return "-" if n is None else "${:,.0f}".format(n)


class _PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(*NAVY)
        self.cell(0, 8, "RealDoor - Readiness Packet", ln=1)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*SOFT)
        self.cell(0, 5, "Assistive, not adjudicative - prepared for human review. Not an eligibility decision.", ln=1)
        self.set_draw_color(*LINE)
        self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1)
        self.ln(4)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*SOFT)
        self.cell(0, 5, "RealDoor does not approve, deny, score, rank, or determine eligibility (CH-DECISION-001). "
                        "Boston-Cambridge-Quincy LIHTC / HUD MTSP FY2026 (eff. 2026-05-01).", align="C")


def _h(pdf, text):
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, text, ln=1)
    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "", 10)


def _para(pdf, text, h=4.6):
    """Robust wrapped paragraph: always starts at the left margin with a valid width."""
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, h, text)


def _row(pdf, k, v, bold=False):
    pdf.set_font("Helvetica", "B" if bold else "", 10)
    pdf.cell(90, 6, k)
    pdf.cell(0, 6, v, ln=1, align="R")


def make_packet(a: dict, title: str | None = None) -> bytes:
    pdf = _PDF()
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()

    ready = a["readiness_status"] == "READY_TO_REVIEW"
    _h(pdf, "Summary")
    _row(pdf, "Reference", str(a.get("household_id") or title or "session"))
    _row(pdf, "Generated", datetime.now().strftime("%Y-%m-%d %H:%M"))
    _row(pdf, "Household size", str(a.get("household_size") or "not stated"))
    _row(pdf, "Annualized income (documented)", _money(a["annualized_income"]), bold=True)
    _row(pdf, "Frozen 60% AMI limit", _money(a.get("threshold")))
    cmp = {"below_or_equal": "at or below limit", "above": "above limit",
           "no_frozen_threshold": "no frozen threshold"}.get(a["comparison"], a["comparison"])
    _row(pdf, "Comparison (not a decision)", cmp)
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*(AMBER if not ready else NAVY))
    pdf.cell(0, 7, "Status: " + ("READY FOR HUMAN REVIEW" if ready else "NEEDS HUMAN REVIEW"), ln=1)
    pdf.set_text_color(*INK)

    # review items
    _h(pdf, "Open review items")
    reasons = a.get("review_reasons", [])
    if not reasons:
        _para(pdf,  "None - no gaps, conflicts, or currency problems were found.")
    else:
        for r in reasons:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, f"- {r}", ln=1)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*SOFT)
            _para(pdf,  "   " + REASON_LABELS.get(r, ""))
            pdf.set_text_color(*INK)

    # documents still needed (informational; does not change readiness)
    needed = a.get("documents_needed_detail") or [{"label": t} for t in a.get("documents_needed", [])]
    _h(pdf, "Documents that would complete this packet")
    if not needed:
        _para(pdf,  "None - the expected document set is present.")
    else:
        for d in needed:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.cell(0, 5, f"- {d['label']}", ln=1)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*SOFT)
        _para(pdf, "Informational only. Missing items do not by themselves change the readiness status.")
        pdf.set_text_color(*INK)

    # income build-up
    b = a.get("income_breakdown", {})
    _h(pdf, "How the income was calculated")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*SOFT)
    _para(pdf,  "Deterministic (no language model). Annualizes the regular wage per HUD Handbook 4350.3 "
                         "(regular hours x rate x pay periods); sums independent sources; overtime/variable pay is "
                         "flagged rather than annualized from a single period.")
    pdf.set_text_color(*INK)
    pdf.ln(1)
    if b.get("wages"):
        _row(pdf, "Wages (regular basis)", _money(b["wages"]))
    if b.get("benefits"):
        _row(pdf, "Benefits (monthly x 12)", _money(b["benefits"]))
    if b.get("gig"):
        _row(pdf, "Gig receipts (monthly x 12, uncorroborated)", _money(b["gig"]))
    _row(pdf, "Annualized income", _money(a["annualized_income"]), bold=True)

    # evidence
    _h(pdf, "Evidence")
    docs = a.get("documents", [])
    for d in docs:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*NAVY)
        emp = f"  -  employer: {d['employer']}" if d.get("employer") else ""
        pdf.cell(0, 6, f"{d.get('document_label', d['document_type'])} ({d['document_id']}){emp}", ln=1)
        pdf.set_text_color(*INK)
        pdf.set_font("Helvetica", "", 9)
        for f in d.get("fields", []):
            label = FIELD_LABEL.get(f["field"], f["field"])
            conf = f"conf {int(f.get('confidence', 1) * 100)}%"
            src = "grounded" if f.get("grounded", True) else "ungrounded"
            pdf.cell(60, 5, f"  {label}")
            pdf.cell(70, 5, str(f["value"]))
            pdf.cell(0, 5, f"{conf} - {src}", ln=1, align="R")
        pdf.ln(1)

    # rule versions relied on
    rv = a.get("rule_versions") or []
    if rv:
        _h(pdf, "Rules relied on (versions)")
        pdf.set_font("Helvetica", "", 8.5)
        for r in rv:
            eff = f" - effective {r['effective_date']}" if r.get("effective_date") else ""
            _para(pdf, f"  {r['rule_id']} ({r.get('authority', '')}){eff}  -  {r.get('source_locator', '')}")

    # consent, actions (audit trail) -- no raw document contents
    audit = a.get("audit") or []
    _h(pdf, "Consent & activity log")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*SOFT)
    _para(pdf, a.get("consent_notice",
        "Values are shown for the applicant's confirmation before use; actions and rule versions "
        "are logged, raw document contents are not."))
    if audit:
        for e in audit[-12:]:
            det = ", ".join(f"{k}={v}" for k, v in (e.get("detail") or {}).items() if k != "consent")
            _para(pdf, f"  {e['ts']}  {e['action']}  {det}")
    pdf.set_text_color(*INK)

    # governance
    _h(pdf, "Data use & provenance")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*SOFT)
    md = C.MODEL_DISCLOSURE
    _para(pdf,
        f"Extraction provider: {md['provider']} ({md['model']}), used for {md['used_for']}. "
        f"Not used for: {md['not_used_for']}. {md['data_use']} "
        "Every extracted value is correctable by the applicant before use.")
    pdf.set_text_color(*INK)

    out = pdf.output()
    return bytes(out)
