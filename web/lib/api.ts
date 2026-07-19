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

const j = (r: Response) => {
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
};

const post = (url: string, body: any) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j);

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
};

export const money = (n: number | null) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
