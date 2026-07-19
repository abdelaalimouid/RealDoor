"""RealDoor API bridge — enterprise surface over the validated pipeline.

Two extraction paths share one deterministic reasoning core:
  * seed households   -> TemplateExtractor (frozen pack, offline, the scored path)
  * uploaded documents -> VisionExtractor (OpenAI, live product; governance-compliant)

The reasoning (income math, thresholds, readiness) is deterministic and identical for
both. The deployed upload API is stateless: the browser owns extracted document records,
corrections, previews, and its activity trail, and submits that state on each request.
Raw uploads are used only while extracting a single request and are never persisted.

Run:  uvicorn api.main:app --reload --port 8000   (from the realdoor/ dir)
"""
from __future__ import annotations
import base64
import tempfile
from pathlib import Path
from typing import Any

import fitz
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from realdoor import config as C
from realdoor import pack
from realdoor import ruleqa
from realdoor import program as program_mod
from realdoor import registry as registry_mod
from realdoor.checklist import DOC_LABEL
from realdoor.extract import extract_document
from realdoor.field_specs import SPECS
from realdoor.readiness import assess
from realdoor.packet import make_packet

ZOOM = 2.0
REASON_LABELS = {
    "PAY_STUB_TOTAL_CONFLICT": "Pay stubs for one job disagree (possible overtime); a person should confirm the recurring amount.",
    "GIG_INCOME_UNCORROBORATED": "Gig income is self-reported and not corroborated by a second source.",
    "EMPLOYMENT_LETTER_EXPIRED": "The employment letter is older than the 60-day currency window.",
    "MISSING_INCOME_EVIDENCE": "No income evidence was provided yet.",
    "NO_FROZEN_THRESHOLD": "Household size falls outside the frozen 2026 MTSP table (sizes 1-8).",
}
DOC_LABELS = {
    "application_summary": "Application summary", "pay_stub": "Pay stub",
    "employment_letter": "Employment letter", "benefit_letter": "Benefit letter",
    "gig_statement": "Gig statement", "unknown": "Document",
}

app = FastAPI(title="RealDoor API", version="1.0",
              description="Assistive application-readiness API. Never decides eligibility.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def require_key(x_api_key: str | None = Header(default=None)):
    if C.API_KEY and x_api_key != C.API_KEY:
        raise HTTPException(401, "invalid or missing X-API-Key")


# ------------------------------------------------------------------ shared view helpers
def _box_px(bbox_bl, ph):
    x0, y0, x1, y1 = bbox_bl
    return [round(x0 * ZOOM, 1), round((ph - y1) * ZOOM, 1),
            round(x1 * ZOOM, 1), round((ph - y0) * ZOOM, 1)]


def _doc_view(d, image_url, overrides=None):
    ov = (overrides or {}).get(d["document_id"], {})
    ph = d.get("page_size_points", [C.PAGE_W, C.PAGE_H])[1]
    fields, injection = [], d.get("quarantined_instruction")
    for f in d["fields"]:
        if f["field"] == "untrusted_instruction_text":
            injection = f["value"]
            continue
        fields.append({
            "field": f["field"], "value": ov.get(f["field"], f["value"]),
            "edited": f["field"] in ov, "confidence": f.get("confidence", 1.0),
            "source": f.get("source", "text"), "grounded": f.get("grounded", True),
            "box_px": _box_px(f["bbox"], ph),
        })
    pw = d.get("page_size_points", [C.PAGE_W, C.PAGE_H])[0]
    return {
        "document_id": d["document_id"], "document_type": d["document_type"],
        "document_label": DOC_LABELS.get(d["document_type"], d["document_type"]),
        "employer": d.get("employer"), "image_url": image_url,
        "image_w": round(pw * ZOOM), "image_h": round(ph * ZOOM), "fields": fields,
        "extraction_confidence": d.get("extraction_confidence"),
        "consistency_checks": d.get("consistency_checks", []),
        "injection": {"present": injection is not None, "quarantined_text": injection},
    }


def _apply_overrides(docs, overrides):
    if not overrides:
        return docs
    return [{**d, "fields": [{**f, "value": (overrides.get(d["document_id"], {})).get(f["field"], f["value"])}
                             for f in d["fields"]]} if overrides.get(d["document_id"]) else d
            for d in docs]


def _assessment(hid, docs, image_url_for, overrides=None, audit=None):
    a = {**assess(hid, _apply_overrides(docs, overrides))}
    a["reasons_detail"] = [{"code": r, "label": REASON_LABELS.get(r, r)} for r in a["review_reasons"]]
    a["documents_needed_detail"] = [{"type": t, "label": DOC_LABEL.get(t, t)} for t in a.get("documents_needed", [])]
    a["rule_versions"] = ruleqa.rule_versions([c.get("rule_id") for c in a["citations"] if c.get("rule_id")])
    a["documents"] = [_doc_view(d, image_url_for(d), overrides) for d in docs]
    a["consent_notice"] = ("You control these documents. Values are shown for your confirmation before use; "
                           "the browser carries the activity trail, and raw document contents are not stored.")
    a["audit"] = audit if audit is not None else []
    return a


def _rq(question, a):
    """Rules Q&A with authoritative citation; eligibility questions are refused."""
    return ruleqa.answer(question, a)


# ------------------------------------------------------------------ meta / disclosure
@app.get("/api/meta")
def meta():
    return {
        "product": "RealDoor — application-readiness copilot",
        "vision_enabled": C.VISION_ENABLED,
        "model_disclosure": C.MODEL_DISCLOSURE,
        "decision_boundary": "Never approves, denies, scores, ranks, or determines eligibility.",
        "program": program_mod.active(),
        "rules": {"threshold": "HUD-MTSP-002 (HUD MTSP FY2026, eff 2026-05-01)",
                  "income": "CH-INCOME-001 (HUD 4350.3 anticipated annual income)",
                  "readiness": "CH-READINESS-001", "currency_window_days": C.CURRENCY_WINDOW_DAYS},
    }


@app.get("/api/program")
def program():
    return program_mod.active()


@app.get("/api/features")
def features():
    return registry_mod.registry()


# ------------------------------------------------------------------ seed households (sample)
_SEED: dict[str, list] = {}


def _seed_docs(hid):
    if hid not in _SEED:
        _SEED[hid] = [extract_document(r) for r in pack.manifest_for(hid)]
    return _SEED[hid]


def _seed_img(d):
    return f"/api/documents/{d['document_id']}/image"


@app.get("/api/households")
def households():
    out = []
    for hid in pack.household_ids():
        a = _assessment(hid, _seed_docs(hid), _seed_img)
        out.append({k: a[k] for k in ("household_id", "household_size", "annualized_income",
                                      "threshold", "comparison", "readiness_status", "review_reasons")})
    return out


@app.get("/api/households/{hid}")
def household(hid: str):
    if hid not in pack.household_ids():
        raise HTTPException(404, "unknown household")
    return _assessment(hid, _seed_docs(hid), _seed_img)


class Reassess(BaseModel):
    overrides: dict[str, dict] = {}


@app.post("/api/households/{hid}/reassess")
def reassess(hid: str, body: Reassess):
    if hid not in pack.household_ids():
        raise HTTPException(404, "unknown household")
    return _assessment(hid, _seed_docs(hid), _seed_img, body.overrides)


class Ask(BaseModel):
    question: str


@app.post("/api/households/{hid}/ask")
def ask(hid: str, body: Ask):
    return _rq(body.question, _assessment(hid, _seed_docs(hid), _seed_img))


@app.get("/api/documents/{doc_id}/image")
def seed_image(doc_id: str):
    row = next((r for r in pack.manifest() if r["document_id"] == doc_id), None)
    if not row:
        raise HTTPException(404, "unknown document")
    d = fitz.open(C.DOCS_DIR / row["file_name"])
    png = d[0].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM)).tobytes("png")
    d.close()
    return Response(png, media_type="image/png")


@app.get("/api/households/{hid}/packet.pdf")
def seed_packet(hid: str):
    if hid not in pack.household_ids():
        raise HTTPException(404, "unknown household")
    a = _assessment(hid, _seed_docs(hid), _seed_img)
    return Response(make_packet(a), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{hid}-readiness-packet.pdf"'})


# ------------------------------------------------------------------ stateless uploads (deployed product)
#
# Vercel may send consecutive requests to different function instances, so module-level
# session dictionaries are not a valid data store.  These endpoints deliberately accept
# the browser's extracted-document state with every downstream request.
_DOCUMENT_TYPES = set(SPECS) | {"unknown"}
_FIELD_NAMES = {field for spec in SPECS.values() for field in spec}
_MAX_DOCUMENTS = 20
_MAX_FIELDS_PER_DOCUMENT = 40


class UploadState(BaseModel):
    documents: list[dict[str, Any]] = Field(default_factory=list)
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    audit: list[dict[str, Any]] = Field(default_factory=list)


class UploadAsk(UploadState):
    question: str


def _bad_upload_state(message: str):
    raise HTTPException(422, f"invalid upload state: {message}")


def _short_text(value: Any, label: str, limit: int, *, nullable: bool = False):
    if nullable and value in (None, ""):
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        _bad_upload_state(f"{label} must be a string up to {limit} characters")
    return value


def _number(value: Any, label: str, *, minimum: float | None = None, maximum: float | None = None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _bad_upload_state(f"{label} must be numeric")
    value = float(value)
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        _bad_upload_state(f"{label} is outside the accepted range")
    return value


def _client_documents(documents: list[dict[str, Any]]):
    """Validate and minimize browser-carried extraction records before calculating.

    This is input validation, not server-side state reconstruction: the records are used
    only for the current request and discarded as soon as the response is returned.
    """
    if len(documents) > _MAX_DOCUMENTS:
        raise HTTPException(413, f"too many documents ({_MAX_DOCUMENTS} maximum)")
    normalized, document_ids = [], set()
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict):
            _bad_upload_state(f"documents[{index}] must be an object")
        did = _short_text(doc.get("document_id"), f"documents[{index}].document_id", 80)
        if did in document_ids:
            _bad_upload_state("document IDs must be unique")
        document_ids.add(did)
        dtype = _short_text(doc.get("document_type"), f"documents[{index}].document_type", 64)
        if dtype not in _DOCUMENT_TYPES:
            _bad_upload_state(f"unsupported document type {dtype!r}")
        raw_fields = doc.get("fields")
        if not isinstance(raw_fields, list) or len(raw_fields) > _MAX_FIELDS_PER_DOCUMENT:
            _bad_upload_state(f"documents[{index}].fields must contain at most {_MAX_FIELDS_PER_DOCUMENT} items")

        fields, field_names = [], set()
        for field_index, field in enumerate(raw_fields):
            if not isinstance(field, dict):
                _bad_upload_state(f"documents[{index}].fields[{field_index}] must be an object")
            name = _short_text(field.get("field"), "field name", 80)
            if name not in _FIELD_NAMES:
                _bad_upload_state(f"unsupported field {name!r}")
            if name in field_names:
                _bad_upload_state("a document cannot contain a field more than once")
            field_names.add(name)
            value = field.get("value")
            if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 500:
                _bad_upload_state(f"{name} has an invalid value")
            bbox = field.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                _bad_upload_state(f"{name}.bbox must contain four coordinates")
            bbox = [_number(v, f"{name}.bbox", minimum=-1, maximum=20_000) for v in bbox]
            fields.append({
                "field": name, "value": value, "page": int(_number(field.get("page", 1), f"{name}.page", minimum=1, maximum=20)),
                "bbox": bbox, "bbox_units": "pdf_points_bottom_left_origin",
                "confidence": _number(field.get("confidence", 1), f"{name}.confidence", minimum=0, maximum=1),
                "grounded": bool(field.get("grounded", True)),
                "source": _short_text(str(field.get("source", "vision")), f"{name}.source", 32),
            })

        page_size = doc.get("page_size_points", [C.PAGE_W, C.PAGE_H])
        if not isinstance(page_size, list) or len(page_size) != 2:
            _bad_upload_state("page_size_points must contain width and height")
        checks = doc.get("consistency_checks", [])
        if not isinstance(checks, list) or len(checks) > 20:
            _bad_upload_state("consistency_checks must be a short list")
        normalized.append({
            "document_id": did,
            "document_type": dtype,
            "file_name": _short_text(str(doc.get("file_name", did)), "file_name", 255),
            "employer": _short_text(doc.get("employer"), "employer", 255, nullable=True),
            "page_size_points": [_number(page_size[0], "page width", minimum=1, maximum=20_000),
                                 _number(page_size[1], "page height", minimum=1, maximum=20_000)],
            "fields": fields,
            "extraction_confidence": (_number(doc["extraction_confidence"], "extraction_confidence", minimum=0, maximum=1)
                                      if doc.get("extraction_confidence") is not None else None),
            "consistency_checks": [c for c in checks if isinstance(c, dict)],
            "quarantined_instruction": _short_text(doc.get("quarantined_instruction"), "quarantined_instruction", 1_000, nullable=True),
        })
    return normalized


def _client_overrides(overrides: dict[str, dict[str, Any]], docs: list[dict[str, Any]]):
    if len(overrides) > len(docs):
        _bad_upload_state("overrides reference too many documents")
    fields_by_document = {d["document_id"]: {f["field"] for f in d["fields"]} for d in docs}
    cleaned = {}
    for did, fields in overrides.items():
        if did not in fields_by_document or not isinstance(fields, dict):
            _bad_upload_state("overrides must reference uploaded document fields")
        if len(fields) > _MAX_FIELDS_PER_DOCUMENT:
            _bad_upload_state("too many field overrides")
        cleaned[did] = {}
        for name, value in fields.items():
            if name not in fields_by_document[did]:
                _bad_upload_state("overrides must reference extracted fields")
            if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 500:
                _bad_upload_state("override has an invalid value")
            cleaned[did][name] = value
    return cleaned


def _client_audit(audit: list[dict[str, Any]]):
    if len(audit) > 100:
        _bad_upload_state("activity trail is too long")
    cleaned = []
    for event in audit:
        if not isinstance(event, dict):
            _bad_upload_state("each activity event must be an object")
        ts = _short_text(event.get("ts"), "activity timestamp", 40)
        action = _short_text(event.get("action"), "activity action", 80)
        detail = event.get("detail", {})
        if not isinstance(detail, dict) or len(detail) > 12:
            _bad_upload_state("activity detail must be a short object")
        cleaned.append({"ts": ts, "action": action,
                        "detail": {str(k)[:80]: str(v)[:200] for k, v in detail.items()}})
    return cleaned


def _upload_assessment(state: UploadState):
    docs = _client_documents(state.documents)
    overrides = _client_overrides(state.overrides, docs)
    audit = _client_audit(state.audit)
    return _assessment("uploaded-documents", docs, lambda _d: "", overrides, audit)


@app.post("/api/uploads/extract", dependencies=[Depends(require_key)])
async def extract_upload(file: UploadFile = File(...), document_type: str | None = Form(default=None)):
    if not C.VISION_ENABLED:
        raise HTTPException(503, "Vision extraction is not configured (set OPENAI_API_KEY).")
    from realdoor.extract_vision import extract_file
    raw = await file.read()
    if len(raw) > 15_000_000:
        raise HTTPException(413, "file too large (15 MB max)")
    suffix = Path(file.filename or "upload.pdf").suffix.lower() or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(raw); tmp.flush()
        doc_path = Path(tmp.name)
        try:
            d = fitz.open(doc_path)
            png = d[0].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM)).tobytes("png")
            d.close()
        except Exception:
            raise HTTPException(400, "could not read the document (send a PDF or image)")
        try:
            rec = extract_file(doc_path, document_type=document_type)
        except Exception as e:
            raise HTTPException(502, f"extraction failed: {e}")
        rec["file_name"] = file.filename or rec["document_id"]
    # The preview is returned to the browser once.  Later requests carry only the
    # normalized extraction record, never the preview image or raw uploaded bytes.
    return {"document": rec,
            "image_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}


@app.post("/api/uploads/reassess")
def upload_reassess(body: UploadState):
    return _upload_assessment(body)


@app.post("/api/uploads/ask")
def upload_ask(body: UploadAsk):
    return _rq(body.question, _upload_assessment(body))


@app.post("/api/uploads/packet.pdf")
def upload_packet(body: UploadState):
    return Response(make_packet(_upload_assessment(body), title="uploaded-documents"), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="realdoor-readiness-packet.pdf"'})
