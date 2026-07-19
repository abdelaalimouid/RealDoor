"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { money, Assessment, Doc } from "@/lib/api";
import { DocViewer } from "@/components/DocViewer";

const STEPS = [
  { n: 1, title: "Profile", sub: "Confirm what we read" },
  { n: 2, title: "Understand", sub: "Cited rules & math" },
  { n: 3, title: "Prepare", sub: "Readiness & packet" },
] as const;

const FIELD_LABEL: Record<string, string> = {
  person_name: "Name", household_size: "Household size", address: "Address",
  application_date: "Application date", pay_date: "Pay date", pay_period_start: "Period start",
  pay_period_end: "Period end", pay_frequency: "Pay frequency", regular_hours: "Regular hours",
  hourly_rate: "Hourly rate", gross_pay: "Gross pay", net_pay: "Net pay", document_date: "Letter date",
  weekly_hours: "Weekly hours", monthly_benefit: "Monthly benefit", benefit_frequency: "Frequency",
  statement_month: "Statement month", gross_receipts: "Gross receipts", platform_fees: "Platform fees",
};
const key = (docId: string, f: string) => `${docId}:${f}`;

export function Journey({
  data, onReassess, onAsk, onConfirm, packetHref, onPacket, onDelete, deleteLabel, onUpload, busyUpload,
}: {
  data: Assessment;
  onReassess: (overrides: Record<string, Record<string, any>>) => Promise<Assessment>;
  onAsk: (q: string) => Promise<any>;
  onConfirm?: (docId: string, field: string) => void;
  packetHref: string;
  onPacket?: () => Promise<void>;
  onDelete?: () => void;
  deleteLabel?: string;
  onUpload?: (files: FileList) => void;
  busyUpload?: boolean;
}) {
  const [step, setStep] = useState(1);
  const [docId, setDocId] = useState<string | null>(data.documents[0]?.document_id ?? null);
  const [field, setField] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, Record<string, any>>>({});
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => { if (!docId && data.documents[0]) setDocId(data.documents[0].document_id); }, [data, docId]);
  const doc = useMemo<Doc | null>(
    () => data.documents.find((d) => d.document_id === docId) ?? data.documents[0] ?? null, [data, docId]);

  const allFields = useMemo(
    () => data.documents.flatMap((d) => d.fields.map((f) => key(d.document_id, f.field))), [data]);
  const allConfirmed = allFields.length > 0 && allFields.every((k) => confirmed.has(k));

  function confirm(docId: string, f: string) {
    setConfirmed((prev) => {
      const n = new Set(prev); n.add(key(docId, f)); return n;
    });
    onConfirm?.(docId, f);
    const done = confirmed.size + 1;
    setLive(`Value confirmed. ${done} of ${allFields.length} values confirmed.`);
  }

  async function edit(documentId: string, f: string, raw: string) {
    const num = Number(raw.replace(/[$,]/g, ""));
    const value = Number.isFinite(num) && raw.trim() !== "" ? num : raw;
    const next = { ...overrides, [documentId]: { ...overrides[documentId], [f]: value } };
    setOverrides(next); setBusy(true);
    const a = await onReassess(next);
    confirm(documentId, f);   // a correction counts as confirmation
    setBusy(false);
    const msg = `Recalculated: ${money(a.annualized_income)} · ${a.readiness_status.replace(/_/g, " ").toLowerCase()}`;
    setLive(msg);
    setToast(msg);
  }

  const ready = data.readiness_status === "READY_TO_REVIEW";

  return (
    <>
      <div aria-live="polite" className="visually-hidden">{live}</div>
      {toast && (
        <div className="chip flash" role="status"
          style={{ position: "fixed", top: 16, left: "50%", transform: "translateX(-50%)", zIndex: 50,
                   background: "var(--navy)", color: "#fff", border: "none", padding: "8px 16px", fontSize: "0.85rem" }}>
          {toast}
        </div>
      )}

      <nav aria-label="Readiness steps" style={{ display: "flex", gap: 10, margin: "6px 0 20px" }}>
        {STEPS.map((s) => (
          <button key={s.n} onClick={() => setStep(s.n)} aria-current={step === s.n ? "step" : undefined}
            className={step === s.n ? "" : "ghost btn"}
            style={{ flex: 1, textAlign: "left", padding: "12px 16px",
                     background: step === s.n ? "var(--navy)" : "transparent", color: step === s.n ? "#fff" : "var(--navy)" }}>
            <div className="mono" style={{ fontSize: "0.72rem", opacity: 0.8 }}>STEP {s.n}</div>
            <div style={{ fontWeight: 700, fontSize: "1.05rem" }}>{s.title}</div>
            <div style={{ fontSize: "0.8rem", opacity: 0.85 }}>{s.sub}</div>
          </button>
        ))}
      </nav>

      <div className="two-col">
        <div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10, alignItems: "center" }}>
            {data.documents.map((d) => (
              <button key={d.document_id} onClick={() => { setDocId(d.document_id); setField(null); }}
                aria-pressed={d.document_id === doc?.document_id}
                className={d.document_id === doc?.document_id ? "" : "ghost btn"}
                style={{ padding: "6px 11px", fontSize: "0.8rem",
                         background: d.document_id === doc?.document_id ? "var(--navy)" : "transparent",
                         color: d.document_id === doc?.document_id ? "#fff" : "var(--navy)" }}>
                {d.document_label}
              </button>
            ))}
            {onUpload && <UploadButton onUpload={onUpload} busy={busyUpload} />}
          </div>
          {doc ? (
            <>
              <DocViewer doc={doc} activeField={field} onField={setField} />
              {doc.employer && (
                <p className="small" style={{ marginTop: 8 }}>
                  Employer read from header: <span className="mono" style={{ color: "var(--navy)" }}>{doc.employer}</span> — used to cluster pay stubs into one job.
                </p>
              )}
            </>
          ) : (onUpload && <Dropzone onUpload={onUpload} busy={busyUpload} />)}
        </div>

        <div className="sheet" style={{ padding: 22, position: "relative" }}>
          {busy && <div className="chip" style={{ position: "absolute", top: 14, right: 14 }} role="status">recomputing…</div>}
          {!doc && <p className="small">Upload a document to begin. Everything you add is confirmed by you before it&apos;s used.</p>}

          {doc && step === 1 && (
            <section aria-label="Profile — confirm extracted values">
              <h3>Confirm what we read from the {doc.document_label.toLowerCase()}</h3>
              <p className="small" style={{ marginBottom: 6 }}>
                Every value is boxed on the page — focus a row to see its source. Correct anything; a value is
                <strong> reused only after you confirm it</strong>.
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
                <span className="chip">{confirmed.size} of {allFields.length} values confirmed</span>
                {doc.extraction_confidence != null && (
                  <span className="chip" title="minimum field confidence, corroborated by internal consistency">
                    doc confidence {(doc.extraction_confidence * 100).toFixed(0)}%
                  </span>
                )}
                {doc.consistency_checks?.filter((ch) => !ch.ok).map((ch) => (
                  <span key={ch.field} className="chip" style={{ color: "var(--amber)", borderColor: "var(--amber)" }} title={ch.note}>
                    ⚑ {ch.field}
                  </span>
                ))}
              </div>
              {doc.fields.map((f) => {
                const k = key(doc.document_id, f.field);
                const isConfirmed = confirmed.has(k);
                return (
                  <div key={f.field} className={`field-row ${field === f.field ? "active" : ""}`}
                    onMouseEnter={() => setField(f.field)} onMouseLeave={() => setField(null)}>
                    <div className="label">
                      {FIELD_LABEL[f.field] ?? f.field}
                      {!f.grounded && <span title="value not located on page" style={{ color: "var(--amber)" }}> · not located</span>}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span className="mono" style={{ fontSize: "0.72rem", color: "var(--ink-soft)" }} aria-label={`confidence ${(f.confidence * 100).toFixed(0)} percent`}>
                        {(f.confidence * 100).toFixed(0)}%
                      </span>
                      <input defaultValue={String(f.value)} aria-label={`${FIELD_LABEL[f.field] ?? f.field} value`}
                        onFocus={() => setField(f.field)}
                        onBlur={(e) => { if (e.target.value !== String(f.value)) edit(doc.document_id, f.field, e.target.value); }}
                        className={`value ${f.edited ? "edited" : ""}`}
                        style={{ font: "inherit", fontFamily: "var(--mono)", fontWeight: 700, border: "1px solid var(--line)",
                                 borderRadius: 4, padding: "5px 8px", width: 130, textAlign: "right", background: "var(--card)",
                                 color: f.edited ? "var(--blue)" : "var(--ink)" }} />
                      <button onClick={() => confirm(doc.document_id, f.field)} disabled={isConfirmed}
                        aria-label={`Confirm ${FIELD_LABEL[f.field] ?? f.field}`}
                        className={isConfirmed ? "" : "ghost btn"}
                        style={{ padding: "5px 9px", fontSize: "0.75rem",
                                 background: isConfirmed ? "var(--green)" : "transparent",
                                 color: isConfirmed ? "#fff" : "var(--navy)", borderColor: isConfirmed ? "var(--green)" : "var(--navy)" }}>
                        {isConfirmed ? "✓ Confirmed" : "Confirm"}
                      </button>
                    </div>
                  </div>
                );
              })}
              <button className="ghost btn" style={{ marginTop: 10, fontSize: "0.82rem" }}
                onClick={() => { doc.fields.forEach((f) => confirm(doc.document_id, f.field)); }}>
                Confirm all on this document
              </button>
              {doc.injection.present && (
                <div className="callout blocked" style={{ marginTop: 16 }}>
                  <div className="h">Embedded instruction ignored</div>
                  <p className="small" style={{ margin: "4px 0 8px" }}>This document contains text addressed to the system. It is quarantined as data and never executed:</p>
                  <code className="mono" style={{ fontSize: "0.8rem", color: "var(--red)" }}>“{doc.injection.quarantined_text}”</code>
                </div>
              )}
            </section>
          )}

          {doc && step === 2 && <Understand data={data} onAsk={onAsk} />}
          {step === 3 && <Prepare data={data} packetHref={packetHref} onPacket={onPacket} onDelete={onDelete} deleteLabel={deleteLabel} allConfirmed={allConfirmed}
                                  confirmedCount={confirmed.size} totalFields={allFields.length} />}
        </div>
      </div>
    </>
  );
}

function UploadButton({ onUpload, busy }: { onUpload: (f: FileList) => void; busy?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  return (<>
    <button className="ghost btn" style={{ padding: "6px 11px", fontSize: "0.8rem", borderStyle: "dashed" }}
      onClick={() => ref.current?.click()} disabled={busy}>{busy ? "reading…" : "+ Upload"}</button>
    <input ref={ref} type="file" accept="application/pdf,image/*" hidden aria-label="Upload a document"
      onChange={(e) => e.target.files && onUpload(e.target.files)} />
  </>);
}

function Dropzone({ onUpload, busy }: { onUpload: (f: FileList) => void; busy?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div className="sheet" role="button" tabIndex={0} aria-label="Upload a document"
      onClick={() => ref.current?.click()} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") ref.current?.click(); }}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (e.dataTransfer.files.length) onUpload(e.dataTransfer.files); }}
      style={{ padding: "56px 24px", textAlign: "center", cursor: "pointer", borderStyle: "dashed",
               borderColor: over ? "var(--navy)" : "var(--line)", background: over ? "var(--muted)" : "var(--card)" }}>
      <div style={{ fontWeight: 700, color: "var(--navy)", fontSize: "1.1rem" }}>{busy ? "Reading your document…" : "Drop a pay stub, benefit or employment letter"}</div>
      <p className="small" style={{ marginTop: 6 }}>PDF or image · synthetic/test documents only · processed in memory, never stored</p>
      <input ref={ref} type="file" accept="application/pdf,image/*" hidden aria-label="Choose a document"
        onChange={(e) => e.target.files && onUpload(e.target.files)} />
    </div>
  );
}

/* ------------------------------------------------------------------ Understand ---- */
function Understand({ data, onAsk }: { data: Assessment; onAsk: (q: string) => Promise<any> }) {
  const b = data.income_breakdown;
  const cmp = data.comparison === "below_or_equal" ? "at or below" : data.comparison === "above" ? "above" : "not comparable to";
  const [q, setQ] = useState("When do the FY 2026 MTSP limits take effect?");
  const [ans, setAns] = useState<any>(null);
  const examples = ["What is the frozen 60% threshold for this household?", "Is the 60-day currency rule a universal LIHTC rule?", "Am I eligible?"];
  return (
    <section aria-label="Understand — cited rules and math">
      <h3>How the income was built, and what rule it meets</h3>
      <p className="small" style={{ marginBottom: 14 }}>
        The math is deterministic (never a language model), grounded in HUD Handbook 4350.3: annualize the{" "}
        <em>regular</em> wage, sum independent sources, flag what can&apos;t be annualized safely.
      </p>
      <div className="sheet ruled" style={{ padding: "6px 14px", marginBottom: 16 }}>
        <Row k={<>Wages — <span className="mono" style={{ fontSize: "0.8rem" }}>regular_hours × rate × periods</span></>} v={money(b.wages)} />
        {b.benefits > 0 && <Row k="Benefits — monthly × 12" v={money(b.benefits)} />}
        {b.gig > 0 && <Row k="Gig receipts — monthly × 12" v={money(b.gig)} flag="uncorroborated" />}
        <hr className="hairline" />
        <Row k="Annualized income" v={money(data.annualized_income)} bold />
      </div>
      <div className="callout" style={{ marginBottom: 18 }}>
        <div className="h">Threshold comparison</div>
        <p style={{ margin: "4px 0 0" }}>
          <span className="mono">{money(data.annualized_income)}</span> is <strong>{cmp}</strong> the frozen FY2026 60% AMI
          limit for a household of {data.household_size ?? "?"}: <span className="mono">{money(data.threshold)}</span>.
        </p>
        <p className="small" style={{ margin: "8px 0 0" }}>
          Source: HUD MTSP FY2026 (HUD-MTSP-002), effective <span className="mono">2026-05-01</span>. A comparison, not an eligibility decision.
        </p>
      </div>

      <h3 style={{ fontSize: "0.95rem", marginBottom: 8 }}>Ask about the rules</h3>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Ask a rules question"
          style={{ flex: 1, font: "inherit", padding: "9px 12px", border: "1px solid var(--line)", borderRadius: 5, background: "var(--card)" }} />
        <button onClick={async () => setAns(await onAsk(q))}>Ask</button>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {examples.map((e) => <button key={e} className="chip" onClick={() => { setQ(e); }} style={{ cursor: "pointer", border: "1px solid var(--line)" }}>{e}</button>)}
      </div>
      {ans && <AnswerCard ans={ans} />}

      <h3 style={{ fontSize: "0.95rem", margin: "18px 0 10px" }}>Reasoning trail</h3>
      <ul className="trail">
        {data.reasoning_ledger.map((s, i) => (<li key={i}><div className="step">{s.step}</div><div className="detail">{describe(s)}</div></li>))}
      </ul>
    </section>
  );
}

function AnswerCard({ ans }: { ans: any }) {
  return (
    <div className={`callout ${ans.refused ? "blocked" : ""}`} style={{ marginBottom: 8 }}>
      <div className="h">{ans.refused ? "RealDoor will not decide that" : "Answer"}</div>
      <p style={{ margin: "4px 0 0" }}>{ans.answer}</p>
      {ans.refused && ans.facts && (
        <div className="sheet" style={{ padding: "8px 12px", marginTop: 10 }}>
          <Row k="Annualized income" v={money(ans.facts.annualized_income)} />
          <Row k="60% AMI threshold" v={money(ans.facts.frozen_60_threshold)} />
          <Row k="Comparison" v={ans.facts.comparison} />
        </div>
      )}
      {ans.citations?.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="small" style={{ fontWeight: 700, color: "var(--navy)" }}>Authoritative citation</div>
          {ans.citations.map((c: any) => (
            <div key={c.rule_id} className="small" style={{ marginTop: 4 }}>
              <span className="mono" style={{ color: "var(--navy)" }}>{c.rule_id}</span>
              {c.effective_date && <> · eff. <span className="mono">{c.effective_date}</span></>} · {c.source_locator}
              {c.source_url && <> · <a href={c.source_url} target="_blank" rel="noreferrer">source</a></>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Row({ k, v, bold, flag }: { k: React.ReactNode; v: string; bold?: boolean; flag?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 0", gap: 12 }}>
      <span style={{ fontWeight: bold ? 700 : 400, color: bold ? "var(--navy)" : "var(--ink)" }}>
        {k} {flag && <span className="chip" style={{ color: "var(--amber)" }}>{flag}</span>}
      </span>
      <span className="mono" style={{ fontWeight: 700, fontSize: bold ? "1.1rem" : "1rem" }}>{v}</span>
    </div>
  );
}

function describe(s: any): React.ReactNode {
  switch (s.step) {
    case "wage": return <>Clustered {s.stubs} pay stub{s.stubs > 1 ? "s" : ""}{s.employer ? <> for <span className="mono">{s.employer}</span></> : ""} into one job; regular basis <span className="mono">{money(s.regular_basis)}</span> / {s.frequency} → <span className="mono">{money(s.annualized)}</span>/yr{s.conflict ? " · totals disagree, flagged" : ""}.</>;
    case "benefit": return <>Benefit <span className="mono">{money(s.monthly)}</span>/mo × 12 → <span className="mono">{money(s.annualized)}</span>/yr.</>;
    case "gig": return <>Gig receipts <span className="mono">{money(s.monthly_receipts)}</span>/mo × 12 → <span className="mono">{money(s.annualized)}</span>/yr — counted but uncorroborated.</>;
    case "currency": return <>Employment letter dated <span className="mono">{s.date}</span> is outside the 60-day window → flagged.</>;
    case "threshold": return s.threshold_60 ? <>Compared <span className="mono">{money(s.annualized)}</span> to the frozen 60% limit <span className="mono">{money(s.threshold_60)}</span> → {s.comparison}.</> : <>Household size outside the frozen table (1–8) → no frozen threshold.</>;
    case "readiness": return <>Final status: <strong>{s.status}</strong>{s.reasons?.length ? ` — ${s.reasons.join(", ")}` : " — no gaps found"}.</>;
    default: return JSON.stringify(s);
  }
}

/* ------------------------------------------------------------------ Prepare ---- */
function Prepare({ data, packetHref, onPacket, onDelete, deleteLabel, allConfirmed, confirmedCount, totalFields }:
  { data: Assessment; packetHref: string; onPacket?: () => Promise<void>; onDelete?: () => void; deleteLabel?: string; allConfirmed: boolean; confirmedCount: number; totalFields: number }) {
  const ready = data.readiness_status === "READY_TO_REVIEW";
  const [packetBusy, setPacketBusy] = useState(false);
  const [packetError, setPacketError] = useState<string | null>(null);

  async function downloadPacket() {
    if (!onPacket) return;
    setPacketBusy(true);
    setPacketError(null);
    try {
      await onPacket();
    } catch {
      setPacketError("Could not build the readiness packet. Please try again.");
    } finally {
      setPacketBusy(false);
    }
  }

  return (
    <section aria-label="Prepare — readiness packet">
      <h3>Readiness packet</h3>
      <div className={`callout ${ready ? "" : "review"}`} style={{ marginBottom: 16 }}>
        <div className="h">{ready ? "Ready for a human reviewer" : "Needs a human to review first"}</div>
        {data.reasons_detail.length === 0
          ? <p style={{ margin: "4px 0 0" }} className="small">No gaps, conflicts, or currency problems were found.</p>
          : <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {data.reasons_detail.map((r) => (<li key={r.code} style={{ marginBottom: 4 }}>
                <span className="mono" style={{ fontSize: "0.78rem", color: "var(--amber)" }}>{r.code}</span> — {r.label}</li>))}
            </ul>}
      </div>

      <h3 style={{ fontSize: "0.95rem", marginBottom: 8 }}>Documents that would complete this packet</h3>
      {data.documents_needed_detail?.length ? (
        <ul style={{ margin: "0 0 16px", paddingLeft: 18 }}>
          {data.documents_needed_detail.map((d) => <li key={d.type} style={{ marginBottom: 4 }}>{d.label}</li>)}
        </ul>
      ) : <p className="small" style={{ marginBottom: 16 }}>The expected document set is present.</p>}

      <details style={{ marginBottom: 16 }}>
        <summary style={{ cursor: "pointer", fontWeight: 700, color: "var(--navy)" }}>Consent &amp; activity log</summary>
        <p className="small" style={{ margin: "8px 0" }}>{data.consent_notice}</p>
        {data.audit?.length > 0 && (
          <ul className="mono" style={{ fontSize: "0.75rem", listStyle: "none", padding: 0, margin: 0 }}>
            {data.audit.slice(-8).map((e, i) => (
              <li key={i} style={{ padding: "2px 0", color: "var(--ink-soft)" }}>
                {e.ts.slice(11, 19)} · {e.action}{e.detail?.field ? ` (${e.detail.field})` : ""}{e.detail?.document_type ? ` (${e.detail.document_type})` : ""}
              </li>
            ))}
          </ul>
        )}
        <div className="small" style={{ marginTop: 8 }}>
          <strong>Rule versions:</strong> {data.rule_versions.map((r) => `${r.rule_id}${r.effective_date ? ` (${r.effective_date})` : ""}`).join(" · ") || "—"}
        </div>
      </details>

      <hr className="hairline" style={{ margin: "6px 0 16px" }} />
      {!allConfirmed && (
        <p className="callout review small" style={{ marginBottom: 10 }}>
          Confirm all values first ({confirmedCount} of {totalFields}) to finalize the packet.
        </p>
      )}
      {packetError && <p className="callout blocked small" style={{ marginBottom: 10 }}>{packetError}</p>}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        {onPacket ? (
          <button className="btn" onClick={downloadPacket} disabled={!allConfirmed || packetBusy}
            aria-disabled={!allConfirmed} style={{ opacity: allConfirmed ? 1 : 0.45 }}>
            {packetBusy ? "Building packet…" : "Download readiness packet (PDF)"}
          </button>
        ) : (
          <a className="btn" href={allConfirmed ? packetHref : undefined} target="_blank" rel="noreferrer"
            aria-disabled={!allConfirmed}
            style={{ opacity: allConfirmed ? 1 : 0.45, pointerEvents: allConfirmed ? "auto" : "none" }}>
            Download readiness packet (PDF)
          </a>
        )}
        {onDelete && <button className="ghost btn" onClick={onDelete}>{deleteLabel ?? "Delete this session"}</button>}
      </div>
      <p className="small" style={{ marginTop: 12 }}>{data.decision_boundary}</p>
    </section>
  );
}
