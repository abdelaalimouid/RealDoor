"""Paths and frozen constants for the RealDoor simulation."""
from __future__ import annotations
import os
from datetime import date
from pathlib import Path

# --- lightweight .env loader (no dependency) -------------------------------------------
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# --- hosted-model (live upload path only; never used for the scored submission) --------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_VISION_MODEL = os.environ.get("REALDOOR_VISION_MODEL", "gpt-4o")
VISION_ENABLED = bool(OPENAI_API_KEY)
# Provider disclosure surfaced in the product (Responsible-AI requirement).
MODEL_DISCLOSURE = {
    "provider": "OpenAI",
    "model": OPENAI_VISION_MODEL,
    "used_for": "field extraction from uploaded documents only",
    "not_used_for": "eligibility, approval, denial, priority, or any math/decision (those are deterministic)",
    "data_use": "processed ephemerally in memory; raw document contents are not persisted or logged; "
                "not used for model training (per OpenAI API terms); synthetic documents only.",
}
SESSION_TTL_SECONDS = int(os.environ.get("REALDOOR_SESSION_TTL", "3600"))
API_KEY = os.environ.get("REALDOOR_API_KEY", "")   # optional gate for the REST API

# Bundled reference data (committed): public income-limit table + rule corpus. Always
# present, so the upload path, rules, and thresholds work in any deployment.
REFERENCE = Path(__file__).resolve().parent / "reference"
MTSP_CSV = REFERENCE / "income_limits.csv"
RULES_JSONL = REFERENCE / "rule_corpus.jsonl"

# Optional sample dataset (documents + gold labels), provided out-of-band and not bundled.
# Set REALDOOR_PACK, or place it at <repo>/data. When absent, sample households are simply
# unavailable; uploads, rules, thresholds, and the packet all still work.
PACK = Path(os.environ.get("REALDOOR_PACK") or Path(__file__).resolve().parents[1] / "data")
DOCS_DIR = PACK / "synthetic_documents" / "documents"
GOLD_DOCS = PACK / "synthetic_documents" / "gold" / "document_gold.jsonl"
MANIFEST = PACK / "synthetic_documents" / "gold" / "document_manifest.csv"
CHECKLISTS = PACK / "evaluation" / "application_checklists.json"
QA_GOLD = PACK / "evaluation" / "qa_gold.jsonl"
ADVERSARIAL = PACK / "evaluation" / "adversarial_tests.jsonl"

# Frozen event conventions (see rules/RULES_README.md).
EVENT_DATE = date(2026, 7, 18)
CURRENCY_WINDOW_DAYS = 60            # evidence current if dated within 60 days of EVENT_DATE
PAGE_W, PAGE_H = 612.0, 792.0       # PDF points; gold uses bottom-left origin
OCR_DPI = 200
TESSDATA_PREFIX = os.environ.get("TESSDATA_PREFIX", "/opt/homebrew/share/tessdata")

# The frozen threshold we score against is the 60% column.
THRESHOLD_RULE_ID = "HUD-MTSP-002"
INCOME_RULE_ID = "CH-INCOME-001"
READINESS_RULE_ID = "CH-READINESS-001"
SAFETY_RULE_ID = "CH-SAFETY-001"
DECISION_RULE_ID = "CH-DECISION-001"
