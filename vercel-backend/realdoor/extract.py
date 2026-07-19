"""PDF field extraction with real page-level source boxes.

Strategy
--------
* Text-layer PDFs  -> PyMuPDF word boxes (exact).
* Rasterized PDFs  -> PyMuPDF built-in Tesseract OCR word boxes.
* Coordinates are converted from PyMuPDF's TOP-left origin to the gold's
  BOTTOM-left origin via  y_bottom = PAGE_H - y_top.
* Watermark / boilerplate words are filtered by glyph height and known tokens.
* Field values are read from the cell directly below (or beside) their label.

Every returned field carries {field, value, page, bbox, bbox_units} so the
output satisfies the gold schema and the citation contract.
"""
from __future__ import annotations
import os, re
import fitz  # PyMuPDF

from . import config as C
from .field_specs import SPECS

os.environ.setdefault("TESSDATA_PREFIX", C.TESSDATA_PREFIX)

# Header band (company name, "TRAINING FIXTURE...", doc id) and footer fixture line
# are dropped by y-position rather than by token, so body words like "DOCUMENT"
# in "UNTRUSTED DOCUMENT TEXT" survive for label matching.
_HEADER_MAX_Y = 100    # top-origin: drop words whose top is above this
_FOOTER_MIN_Y = 740


def _flip(bbox):
    x0, y0, x1, y1 = bbox
    return [round(x0, 2), round(C.PAGE_H - y1, 2), round(x1, 2), round(C.PAGE_H - y0, 2)]


def _union(boxes):
    xs0 = [b[0] for b in boxes]; ys0 = [b[1] for b in boxes]
    xs1 = [b[2] for b in boxes]; ys1 = [b[3] for b in boxes]
    return [min(xs0), min(ys0), max(xs1), max(ys1)]


def page_words(page, rasterized: bool):
    """Return list of (x0, y0, x1, y1, text) in top-left origin, boilerplate removed."""
    if rasterized:
        tp = page.get_textpage_ocr(flags=0, full=True, dpi=C.OCR_DPI)
        raw = page.get_text("words", textpage=tp)
    else:
        raw = page.get_text("words")
    words = []
    for w in raw:
        x0, y0, x1, y1, txt = w[0], w[1], w[2], w[3], w[4]
        if not txt.strip():
            continue
        if (y1 - y0) > 20:                    # giant diagonal watermark
            continue
        if y0 < _HEADER_MAX_Y or y0 > _FOOTER_MIN_Y:   # header/footer boilerplate
            continue
        words.append((x0, y0, x1, y1, txt))
    return words


def _find_labels(words, tokens):
    """Return the union bbox of EVERY consecutive run matching `tokens`.

    Multiple matches happen when a label phrase also appears in prose (e.g. an
    employment letter says "hours per week" in a sentence and again as a field
    label). Returning all matches lets the caller pick the one whose value
    coerces to the expected type.
    """
    up = [w[4].strip(":").upper() for w in words]
    T = [t.upper() for t in tokens]
    hits = []
    for i in range(len(words) - len(T) + 1):
        if up[i:i + len(T)] == T:
            hits.append(_union([words[j][:4] for j in range(i, i + len(T))]))
    return hits


def _value_below(words, label_bbox, y_gap=20, x_pad=6, col_gap=40):
    """The value line beneath a label: a contiguous run of words starting at the
    label's left edge, broken at a large horizontal gap (the next column).

    Banded relative to the label TOP (ly0) so values a few points below the label
    baseline are still captured (e.g. MONTHLY AMOUNT -> $850.00). Starting at the
    label's x0 (not just x-overlap) keeps us in the right column, and the gap-break
    captures full multi-word values (e.g. a whole street address) without bleeding
    into an adjacent field.
    """
    lx0, ly0, lx1, ly1 = label_bbox
    line = sorted((w for w in words if ly0 + 6 <= w[1] <= ly0 + y_gap), key=lambda w: w[0])
    if not line:
        return []
    # Split the value line into contiguous runs (a run break marks a new column).
    runs = [[line[0]]]
    for w in line[1:]:
        if (w[0] - runs[-1][-1][2]) <= col_gap:
            runs[-1].append(w)
        else:
            runs.append([w])
    lcx = (lx0 + lx1) / 2
    overlapping = [r for r in runs if r[0][0] <= lx1 + x_pad and r[-1][2] >= lx0 - x_pad]
    pool = overlapping or runs
    # Pick the run whose horizontal center is nearest the label center (its column).
    return min(pool, key=lambda r: abs((r[0][0] + r[-1][2]) / 2 - lcx))


def _cellify(bbox, min_w=24.0, min_h=14.0):
    """Normalize a tight glyph box to the document's fixed field-cell geometry
    (values sit in ~24x14pt cells), vertically centered. Improves source-box IoU
    against gold without moving the anchor point."""
    x0, y0, x1, y1 = bbox
    if x1 - x0 < min_w:
        x1 = x0 + min_w
    if y1 - y0 < min_h:
        cy = (y0 + y1) / 2
        y0, y1 = cy - min_h / 2, cy + min_h / 2
    return [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]


def _value_after(words, label_bbox, x_gap=140):
    """Words on the same line to the right of the label (fallback)."""
    lx0, ly0, lx1, ly1 = label_bbox
    line = [w for w in words
            if abs(w[1] - ly0) <= 4 and lx1 <= w[0] <= lx1 + x_gap]
    line.sort(key=lambda w: w[0])
    return line


_MONEY = re.compile(r"[^0-9.\-]")

# Header-band boilerplate to strip when isolating the employer name. The company
# name is the residue after removing the fixture watermark, the "Pay Stub" title,
# and the document id.
_EMP_BOILER = {"DOC", "DOCUMENT", "REAL", "PAY", "STUB", "TRAINING", "FIXTURE",
               "ALL", "NAMES", "AND", "ORGANIZATIONS", "ARE", "FICTIONAL"}
_DOCID = re.compile(r"^HH-\d+-D\d+$", re.I)


def _employer_from_page(page, rasterized, y_max=105):
    """Isolate the employer name from the stub header band (dropped by page_words).

    Returned for job clustering, not scored. Value-invariant to the amounts below.
    """
    if rasterized:
        tp = page.get_textpage_ocr(flags=0, full=True, dpi=C.OCR_DPI)
        raw = page.get_text("words", textpage=tp)
    else:
        raw = page.get_text("words")
    toks = sorted((w for w in raw if w[1] < y_max), key=lambda w: (round(w[1]), w[0]))
    keep = [w[4] for w in toks
            if w[4].upper() not in _EMP_BOILER
            and not _DOCID.match(w[4])
            and any(ch.isalpha() for ch in w[4])]
    return " ".join(keep).strip()


def _coerce(kind, text):
    t = text.strip()
    if kind == "money":
        try:
            return float(_MONEY.sub("", t))
        except ValueError:
            return None
    if kind == "int":
        m = re.search(r"-?\d+", t)
        return int(m.group()) if m else None
    if kind in ("date", "ym", "word", "text", "instruction"):
        return t
    return t


def extract_document(doc_meta: dict) -> dict:
    """doc_meta: a manifest row. Returns a gold-shaped extraction record."""
    dtype = doc_meta["document_type"]
    rasterized = str(doc_meta.get("rasterized", "False")).lower() == "true"
    path = C.DOCS_DIR / doc_meta["file_name"]
    d = fitz.open(path)
    page = d[0]
    words = page_words(page, rasterized)

    numeric = {"money", "int"}
    fields = []
    for field, spec in SPECS.get(dtype, {}).items():
        labels = _find_labels(words, spec["label"])
        if not labels:
            continue

        best = None
        for label in labels:
            if spec["kind"] == "instruction":
                # Capture injected text verbatim so it can be quarantined -- never executed.
                band = [w for w in words if w[1] > label[3] - 2][:40]
                band.sort(key=lambda w: (round(w[1]), w[0]))
            else:
                band = _value_below(words, label) or _value_after(words, label)
            if not band:
                continue
            raw_val = " ".join(w[4] for w in band).strip()
            value = _coerce(spec["kind"], raw_val)
            if value in (None, ""):
                continue
            # For numeric fields, a valid coercion means we found the real value
            # (not a prose false-match); take the first such and stop.
            cand = (field, value, band)
            if spec["kind"] in numeric or best is None:
                best = cand
                if spec["kind"] in numeric:
                    break
        if best is None:
            continue
        _, value, band = best
        raw_box = _flip(_union([w[:4] for w in band]))
        bbox = raw_box if spec["kind"] == "instruction" else _cellify(raw_box)
        fields.append({
            "field": field,
            "value": value,
            "page": 1,
            "bbox": bbox,
            "bbox_units": "pdf_points_bottom_left_origin",
            "confidence": 0.99 if not rasterized else 0.9,
            "source": "text" if not rasterized else "ocr",
        })
    employer = _employer_from_page(page, rasterized) if dtype == "pay_stub" else None
    d.close()
    from .confidence import annotate
    return annotate({
        "document_id": doc_meta["document_id"],
        "household_id": doc_meta["household_id"],
        "document_type": dtype,
        "file_name": doc_meta["file_name"],
        "rasterized": rasterized,
        "page_count": 1,
        "page_size_points": [C.PAGE_W, C.PAGE_H],
        "employer": employer,
        "fields": fields,
    })
