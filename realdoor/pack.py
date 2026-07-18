"""Loaders for the frozen organizer pack (rules, MTSP table, gold, checklists)."""
from __future__ import annotations
import csv, json
from functools import lru_cache
from . import config as C


def _jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=1)
def rules() -> dict:
    rows = _jsonl(C.RULES_JSONL)
    return {r["rule_id"]: r for r in rows}


@lru_cache(maxsize=1)
def mtsp() -> dict:
    """household_size -> {threshold_60, limit_50, source_url, page, ...}"""
    out = {}
    with open(C.MTSP_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[int(row["household_size"])] = {
                "threshold_60": float(row["income_limit_60_percent"]),
                "limit_50": float(row["income_limit_50_percent"]),
                "hud_area": row["hud_area"],
                "effective_date": row["effective_date"],
                "source_url": row["source_url"],
                "source_page": int(row["source_pdf_page"]),
            }
    return out


def threshold_for(household_size: int):
    return mtsp().get(int(household_size))


@lru_cache(maxsize=1)
def checklists() -> dict:
    with open(C.CHECKLISTS, encoding="utf-8") as f:
        return {c["household_id"]: c for c in json.load(f)}


@lru_cache(maxsize=1)
def manifest() -> list:
    with open(C.MANIFEST, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def manifest_for(household_id: str) -> list:
    return [r for r in manifest() if r["household_id"] == household_id]


def household_ids() -> list:
    seen = []
    for r in manifest():
        if r["household_id"] not in seen:
            seen.append(r["household_id"])
    return seen


def gold_docs() -> list:
    return _jsonl(C.GOLD_DOCS)


def qa_gold() -> list:
    return _jsonl(C.QA_GOLD)


def adversarial() -> list:
    return _jsonl(C.ADVERSARIAL)
