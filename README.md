# RealDoor

**An application-readiness copilot for affordable housing.** RealDoor turns a household's
documents into a human-confirmed, evidence-linked readiness packet: it extracts fields with
page-level source boxes, annualizes income deterministically, compares it against a frozen
income limit, flags missing or expired documents, and answers rule questions with citations.

RealDoor is **assistive, not adjudicative**. It never approves, denies, scores, ranks, or
determines eligibility.

> The AI extracts, explains, retrieves, calculates, and prepares. The person confirms.
> A qualified human decides.

---

## How it works

RealDoor is built around one principle: **a language model is used only to read documents;
every calculation, threshold comparison, and readiness decision is deterministic and
model-free.** Two extraction backends feed one deterministic reasoning core.

```
            ┌──────────────── extraction (pluggable) ────────────────┐
 documents →│  TemplateExtractor  — layout/label geometry, offline   │ 
            │  VisionExtractor    — OpenAI vision, arbitrary uploads │
            └───────────────────────────┬────────────────────────────┘
                 normalized fields + source boxes + confidence
                            ┌───────────▼────────────┐
                            │   DETERMINISTIC CORE   │  no model past this line
                            │  income (HUD 4350.3)   │
                            │  income-limit lookup   │
                            │  readiness + reasons   │
                            │  document checklist    │
                            │  rules Q&A (corpus)    │
                            │  confidence calibration│
                            └───────────┬────────────┘
                  FastAPI   ────────────┼─────────────  Next.js UI
       sessions · packet · audit                Profile → Understand → Prepare
```

### Extraction
- **Template extractor** (`realdoor/extract.py`) locates fields by label text and column
  geometry; exact and fully offline. It reads PDF text layers directly and falls back to OCR
  for rasterized pages, and returns each value with a page-level bounding box.
- **Vision extractor** (`realdoor/extract_vision.py`) handles arbitrary uploaded documents
  with an OpenAI vision model. It extracts **only allowlisted fields** plus a verbatim
  snippet, then **grounds** each value to real page coordinates by locating the snippet in the
  page text (with an OCR fallback for scans). Embedded instructions are quarantined and never
  executed; no protected traits are inferred.

### Reasoning (deterministic)
- **Income** (`readiness.py`) follows HUD Handbook 4350.3 anticipated-annual-income: the
  regular wage (`regular_hours × hourly_rate × pay periods`) is annualized; independent
  sources are summed; overtime/variable pay that cannot be annualized from a single period is
  flagged for review rather than guessed. Pay stubs are clustered into jobs by employer, with
  OCR-tolerant fuzzy matching so noisy reads are not double-counted.
- **Income-limit comparison** looks up the frozen limit for the household size and reports
  `below_or_equal` / `above` — a comparison, never a decision.
- **Readiness** returns `READY_TO_REVIEW` or `NEEDS_REVIEW` with explicit, evidence-linked
  reasons (income conflicts, uncorroborated income, expired documents).
- **Document checklist** (`checklist.py`) flags documents that would complete the packet
  (informational; it never changes readiness).
- **Rules Q&A** (`ruleqa.py`) answers questions from a frozen rule corpus, always with an
  authoritative citation; questions that ask for an eligibility decision are refused.
- **Confidence calibration** (`confidence.py`) corroborates the raw extractor confidence with
  internal-consistency checks so that confidence orders correctly.

### Product surface
- **API** (`api/`) — a FastAPI service with ephemeral upload sessions (raw documents are never
  persisted), a hard `DELETE`, a downloadable **PDF readiness packet**, a consent/action/rule-
  version **audit log**, a **feature registry**, and program configuration.
- **Web** (`web/`) — a Next.js interface (a three-step Profile → Understand → Prepare journey)
  that is presentation-only; all logic lives in the `realdoor/` package. WCAG 2.2 AA:
  keyboard-complete, visible focus, `aria-live` status, no color-only status.

---

## Running it

### Prerequisites
- Python 3.12, Node 18+, and Tesseract (`brew install tesseract`) for OCR.
- A reference dataset directory (income-limit table, rule corpus, sample documents, gold
  labels). It is provided out-of-band and is **not** bundled. Set `REALDOOR_PACK` to its path,
  or place it at `./data`.
- For the upload path, an OpenAI API key.

```bash
# 1) Python deps + config
python -m pip install -r requirements.txt
export TESSDATA_PREFIX=/opt/homebrew/share/tessdata          # macOS Tesseract data
export REALDOOR_PACK=/path/to/reference/data                 # or symlink ./data
cp .env.example .env                                         # add OPENAI_API_KEY for uploads

# 2) API
uvicorn api.main:app --port 8000

# 3) Web (separate terminal)
cd web && npm install && npm run dev                          # http://localhost:3000
```

The web app proxies `/api/*` to the API (`REALDOOR_API`, default `http://127.0.0.1:8000`).

### API (selected)
| Method & path | Purpose |
|---|---|
| `POST /api/sessions` | open an ephemeral upload session |
| `POST /api/sessions/{id}/documents` | upload a document (vision extraction) |
| `POST /api/sessions/{id}/reassess` | recompute after a field correction |
| `POST /api/sessions/{id}/ask` | rules Q&A (eligibility questions are refused) |
| `GET  /api/sessions/{id}/packet.pdf` | download the readiness packet |
| `DELETE /api/sessions/{id}` | erase all session data |
| `GET  /api/program`, `/api/features`, `/api/meta` | program config, feature registry, disclosure |

---

## Testing

```bash
python -m unittest discover -s tests -v   # seed correctness, clustering, red-team, harnesses
python -m realdoor.evaluate               # scorecard against the gold labels
python -m realdoor.robustness 5000 42     # property-based generalization (independent oracle)
python -m realdoor.perturb 300 42         # end-to-end extraction on freshly rendered documents
python -m realdoor.confidence             # confidence calibration report
```

The reasoning core is validated to 100% against the gold labels and generalizes on tens of
thousands of randomized households and thousands of perturbed documents.

---

## Project layout

```
realdoor/   deterministic core: config, extraction, income/threshold, readiness,
            rules Q&A, checklist, confidence, safety, packet, pipeline, harnesses
api/        FastAPI service (sessions, uploads, packet, audit, program, features)
web/        Next.js interface (Profile → Understand → Prepare)
tests/      regression + generalization suite
Dockerfile  container image for the API
```

## Deployment

- **API** — `docker build -t realdoor-api .` then run with `OPENAI_API_KEY` and the reference
  data provided as a volume or baked into the image.
- **Web** — deploy `web/` (e.g. Vercel); set `REALDOOR_API` to the API URL.

## License

[MIT](LICENSE) © 2026 Abdelaali Mouid.
