"""RealDoor API bridge — enterprise surface over the validated pipeline.

Two extraction paths share one deterministic reasoning core:
  * seed households   -> TemplateExtractor (frozen pack, offline, the scored path)
  * uploaded documents -> VisionExtractor (OpenAI, live product; governance-compliant)

The reasoning (income math, thresholds, readiness) is deterministic and identical for
both. Sessions are in-memory and ephemeral: raw uploads are not written to disk, and
DELETE wipes everything. Integrators can drive this API standalone or embed it.

Run:  uvicorn api.main:app --reload --port 8000   (from the realdoor/ dir)
"""
from __future__ import annotations
import tempfile
import time
import uuid
from pathlib import Path

import fitz
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from realdoor import config as C
from realdoor import pack
from realdoor import ruleqa
from realdoor import program as program_mod
from realdoor import registry as registry_mod
from realdoor.checklist import DOC_LABEL
from realdoor.extract import extract_document
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
    a["consent_notice"] = ("You control this session. Values are shown for your confirmation before use; "
                           "actions and rule versions are logged, raw document contents are not.")
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


# ------------------------------------------------------------------ upload sessions (live)
_SESSIONS: dict[str, dict] = {}


def _log(s, action, detail=None):
    """Append an action to the session audit trail. Records consent/actions/rule versions
    only -- never raw document contents (governance: CONSENT AND CORRECTION)."""
    s.setdefault("audit", []).append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                      "action": action, "detail": detail or {}})


def _purge():
    now = time.time()
    for sid in [s for s, v in _SESSIONS.items() if now - v["created"] > C.SESSION_TTL_SECONDS]:
        _SESSIONS.pop(sid, None)


def _session(sid):
    _purge()
    if sid not in _SESSIONS:
        raise HTTPException(404, "session not found or expired")
    return _SESSIONS[sid]


def _sess_img(sid):
    return lambda d: f"/api/sessions/{sid}/documents/{d['document_id']}/image"


@app.post("/api/sessions", dependencies=[Depends(require_key)])
def create_session():
    sid = uuid.uuid4().hex[:12]
    s = {"created": time.time(), "docs": [], "images": {}, "overrides": {}, "audit": []}
    _log(s, "session_created", {"consent": "renter opened a private, ephemeral session"})
    _SESSIONS[sid] = s
    return {"session_id": sid, "ttl_seconds": C.SESSION_TTL_SECONDS,
            "vision_enabled": C.VISION_ENABLED, "disclosure": C.MODEL_DISCLOSURE}


@app.post("/api/sessions/{sid}/documents", dependencies=[Depends(require_key)])
async def upload(sid: str, file: UploadFile = File(...), document_type: str | None = Form(default=None)):
    s = _session(sid)
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
    s["docs"].append(rec)
    s["images"][rec["document_id"]] = png
    _log(s, "document_added", {"document_id": rec["document_id"], "document_type": rec["document_type"],
                               "fields_extracted": len(rec["fields"]),
                               "injection_quarantined": rec.get("quarantined_instruction") is not None})
    return {"document": _doc_view(rec, _sess_img(sid)(rec)),
            "assessment": _assessment(sid, s["docs"], _sess_img(sid), s["overrides"], s["audit"])}


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = _session(sid)
    return _assessment(sid, s["docs"], _sess_img(sid), s["overrides"], s["audit"])


@app.post("/api/sessions/{sid}/reassess")
def session_reassess(sid: str, body: Reassess):
    s = _session(sid)
    for did, fields in body.overrides.items():
        for f in fields:
            if f not in (s["overrides"].get(did) or {}):
                _log(s, "field_corrected", {"document_id": did, "field": f})
    s["overrides"] = body.overrides
    return _assessment(sid, s["docs"], _sess_img(sid), s["overrides"], s["audit"])


class Confirm(BaseModel):
    document_id: str
    field: str


@app.post("/api/sessions/{sid}/confirm")
def session_confirm(sid: str, body: Confirm):
    s = _session(sid)
    _log(s, "field_confirmed", {"document_id": body.document_id, "field": body.field})
    return {"logged": True, "audit": s["audit"]}


@app.post("/api/sessions/{sid}/ask")
def session_ask(sid: str, body: Ask):
    s = _session(sid)
    a = _assessment(sid, s["docs"], _sess_img(sid), s["overrides"])
    res = _rq(body.question, a)
    _log(s, "rules_question_asked", {"question": body.question[:200], "refused": res.get("refused", False)})
    return res


@app.get("/api/sessions/{sid}/documents/{doc_id}/image")
def session_image(sid: str, doc_id: str):
    s = _session(sid)
    if doc_id not in s["images"]:
        raise HTTPException(404, "unknown document")
    return Response(s["images"][doc_id], media_type="image/png")


@app.get("/api/sessions/{sid}/packet.pdf")
def session_packet(sid: str):
    s = _session(sid)
    _log(s, "packet_exported", {})
    a = _assessment(sid, s["docs"], _sess_img(sid), s["overrides"], s["audit"])
    return Response(make_packet(a, title=sid), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="realdoor-packet-{sid}.pdf"'})


@app.delete("/api/sessions/{sid}", dependencies=[Depends(require_key)])
def delete_session(sid: str):
    existed = _SESSIONS.pop(sid, None) is not None
    return {"deleted": existed, "session_id": sid,
            "note": "All extracted values and cached images for this session were erased from memory."}
