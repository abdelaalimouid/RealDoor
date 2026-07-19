export type Field = {
  field: string;
  value: string | number;
  edited: boolean;
  confidence: number;
  source: string;
  grounded: boolean;
  box_px: [number, number, number, number];
};

export type Doc = {
  document_id: string;
  document_type: string;
  document_label: string;
  file_name: string;
  employer: string | null;
  image_url: string;
  image_w: number;
  image_h: number;
  fields: Field[];
  extraction_confidence: number | null;
  consistency_checks: { field: string; ok: boolean; note: string }[];
  injection: { present: boolean; quarantined_text: string | null };
};

export type LedgerStep = Record<string, any> & { step: string };

export type Assessment = {
  household_id: string;
  household_size: number;
  annualized_income: number;
  income_breakdown: { wages: number; benefits: number; gig: number };
  threshold: number | null;
  comparison: string;
  readiness_status: "READY_TO_REVIEW" | "NEEDS_REVIEW";
  review_reasons: string[];
  reasons_detail: { code: string; label: string }[];
  documents_needed: string[];
  documents_needed_detail: { type: string; label: string }[];
  rule_versions: { rule_id: string; authority: string; effective_date: string | null; source_url: string; source_locator: string }[];
  reasoning_ledger: LedgerStep[];
  citations: any[];
  documents: Doc[];
  consent_notice: string;
  audit: { ts: string; action: string; detail: Record<string, any> }[];
  decision_boundary: string;
};

export type HouseholdSummary = {
  household_id: string;
  household_size: number;
  annualized_income: number;
  threshold: number | null;
  comparison: string;
  readiness_status: "READY_TO_REVIEW" | "NEEDS_REVIEW";
  review_reasons: string[];
};

/**
 * The normalized record returned by the hosted upload extractor. It deliberately
 * excludes raw upload bytes and the browser-only preview image.
 */
export type ExtractedDocument = {
  document_id: string;
  document_type: string;
  file_name: string;
  employer: string | null;
  page_size_points: [number, number];
  fields: Array<Record<string, any>>;
  extraction_confidence?: number | null;
  consistency_checks?: Array<Record<string, any>>;
  quarantined_instruction?: string | null;
};

export type UploadExtraction = {
  document: ExtractedDocument;
  /** Browser-held preview returned only with the extraction response. */
  image_url: string;
};

export type UploadAuditEvent = {
  ts: string;
  action: string;
  detail: Record<string, string>;
};

const j = (r: Response) => {
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
};

const post = (url: string, body: any) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j);

const uploadState = (
  documents: ExtractedDocument[],
  overrides: Record<string, Record<string, any>> = {},
  audit: UploadAuditEvent[] = [],
) => ({ documents, overrides, audit });

/**
 * Local development keeps the original session-based sample API. The deployed
 * workspace uses the stateless Vercel API, whose function instances share no memory.
 */
export const usesStatelessUploads = () => {
  if (typeof window === "undefined") return false;
  return !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
};

export async function downloadUploadPacket(
  documents: ExtractedDocument[],
  overrides: Record<string, Record<string, any>>,
  audit: UploadAuditEvent[],
) {
  const r = await fetch("/api/uploads/packet.pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(uploadState(documents, overrides, audit)),
  });
  if (!r.ok) throw new Error(`${r.status}`);
  const url = URL.createObjectURL(await r.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "realdoor-readiness-packet.pdf";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

export const api = {
  meta: () => fetch("/api/meta").then(j),
  program: () => fetch("/api/program").then(j),
  features: () => fetch("/api/features").then(j),
  // sample seed households
  households: (): Promise<HouseholdSummary[]> => fetch("/api/households").then(j),
  household: (id: string): Promise<Assessment> => fetch(`/api/households/${id}`).then(j),
  reassess: (id: string, overrides: Record<string, Record<string, any>>): Promise<Assessment> =>
    post(`/api/households/${id}/reassess`, { overrides }),
  ask: (id: string, question: string) => post(`/api/households/${id}/ask`, { question }),
  householdPacket: (id: string) => `/api/households/${id}/packet.pdf`,

  // live upload sessions
  createSession: (): Promise<{ session_id: string; vision_enabled: boolean; disclosure: any }> =>
    post("/api/sessions", {}),
  uploadDoc: (sid: string, file: File): Promise<{ document: Doc; assessment: Assessment }> => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`/api/sessions/${sid}/documents`, { method: "POST", body: fd }).then(j);
  },
  session: (sid: string): Promise<Assessment> => fetch(`/api/sessions/${sid}`).then(j),
  sessionReassess: (sid: string, overrides: Record<string, Record<string, any>>): Promise<Assessment> =>
    post(`/api/sessions/${sid}/reassess`, { overrides }),
  sessionAsk: (sid: string, question: string) => post(`/api/sessions/${sid}/ask`, { question }),
  confirmField: (sid: string, document_id: string, field: string) =>
    post(`/api/sessions/${sid}/confirm`, { document_id, field }),
  sessionPacket: (sid: string) => `/api/sessions/${sid}/packet.pdf`,
  deleteSession: (sid: string) => fetch(`/api/sessions/${sid}`, { method: "DELETE" }).then(j),

  // hosted upload flow: all state is supplied by the browser on every request
  extractUpload: (file: File): Promise<UploadExtraction> => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch("/api/uploads/extract", { method: "POST", body: fd }).then(j);
  },
  uploadReassess: (
    documents: ExtractedDocument[],
    overrides: Record<string, Record<string, any>> = {},
    audit: UploadAuditEvent[] = [],
  ): Promise<Assessment> => post("/api/uploads/reassess", uploadState(documents, overrides, audit)),
  uploadAsk: (
    documents: ExtractedDocument[],
    overrides: Record<string, Record<string, any>> = {},
    audit: UploadAuditEvent[] = [],
    question: string,
  ) => post("/api/uploads/ask", { ...uploadState(documents, overrides, audit), question }),
};

export const money = (n: number | null) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
