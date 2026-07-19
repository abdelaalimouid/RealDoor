"""Per-document-type field label anchors.

Each field maps to the label token sequence that sits directly ABOVE (or left of)
its value in the synthetic layout. The extractor finds the label, then reads the
value in the cell immediately below it. Labels are matched case-insensitively.

`kind` drives value coercion: text | int | money | date | word | ym | instruction.
"""

SPECS = {
    "application_summary": {
        "person_name":      {"label": ["APPLICANT"], "kind": "text"},
        "household_size":   {"label": ["HOUSEHOLD", "SIZE"], "kind": "int"},
        "address":          {"label": ["ADDRESS"], "kind": "text"},
        "application_date": {"label": ["APPLICATION", "DATE"], "kind": "date"},
    },
    "pay_stub": {
        "person_name":      {"label": ["EMPLOYEE"], "kind": "text"},
        "pay_date":         {"label": ["PAY", "DATE"], "kind": "date"},
        "pay_period_start": {"label": ["PAY", "PERIOD"], "kind": "date"},
        "pay_period_end":   {"label": ["THROUGH"], "kind": "date"},
        "pay_frequency":    {"label": ["PAY", "FREQUENCY"], "kind": "word"},
        "regular_hours":    {"label": ["REGULAR", "HOURS"], "kind": "money"},
        "hourly_rate":      {"label": ["HOURLY", "RATE"], "kind": "money"},
        "gross_pay":        {"label": ["GROSS", "PAY"], "kind": "money"},
        "net_pay":          {"label": ["NET", "PAY"], "kind": "money"},
        "untrusted_instruction_text": {"label": ["UNTRUSTED", "DOCUMENT", "TEXT"], "kind": "instruction"},
    },
    "employment_letter": {
        "person_name":   {"label": ["EMPLOYEE"], "kind": "text"},
        "document_date": {"label": ["LETTER", "DATE"], "kind": "date"},
        "weekly_hours":  {"label": ["HOURS", "PER", "WEEK"], "kind": "money"},
        "hourly_rate":   {"label": ["HOURLY", "RATE"], "kind": "money"},
    },
    "benefit_letter": {
        "person_name":      {"label": ["RECIPIENT"], "kind": "text"},
        "document_date":    {"label": ["LETTER", "DATE"], "kind": "date"},
        "monthly_benefit":  {"label": ["MONTHLY", "AMOUNT"], "kind": "money"},
        "benefit_frequency":{"label": ["FREQUENCY"], "kind": "word"},
    },
    "gig_statement": {
        "person_name":    {"label": ["WORKER"], "kind": "text"},
        "statement_month":{"label": ["STATEMENT", "MONTH"], "kind": "ym"},
        "gross_receipts": {"label": ["GROSS", "RECEIPTS"], "kind": "money"},
        "platform_fees":  {"label": ["PLATFORM", "FEES"], "kind": "money"},
        "untrusted_instruction_text": {"label": ["UNTRUSTED", "DOCUMENT", "TEXT"], "kind": "instruction"},
    },
}
