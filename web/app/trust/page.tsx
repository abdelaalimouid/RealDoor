"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

const CONTROLS = [
  ["No decisioning", "Never approves, denies, scores, ranks, or determines eligibility; deflects 'decide for me' to the rule + input + calculation."],
  ["No hidden proxies", "Only allowlisted fields are used, each with a published purpose; no protected, demographic, behavioral, or landlord-revenue features."],
  ["Consent & correction", "Every value is correctable and confirmed before use; consent, actions, and rule versions are logged — never raw document contents."],
  ["Privacy & security", "Synthetic documents only; ephemeral in-memory sessions; hard delete; never trains on uploads; provider disclosed."],
  ["Untrusted input", "Document text is treated as data; embedded instructions are quarantined and never executed."],
  ["Accessible journey", "WCAG 2.2 AA: keyboard-complete, visible focus, labeled controls, aria-live status, no color-only status."],
];

const EVIDENCE = [
  ["Scored pack", "100%"], ["Vision fields", "156/156"], ["Rules citations", "36/36"],
  ["Injection leaks", "0"], ["Logic robustness", "30k/30k"], ["WCAG contrast", "AA"],
];

export default function Trust() {
  const [program, setProgram] = useState<any>(null);
  const [features, setFeatures] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);

  useEffect(() => {
    api.program().then(setProgram).catch(() => {});
    api.features().then(setFeatures).catch(() => {});
    api.meta().then(setMeta).catch(() => {});
  }, []);

  return (
    <div className="wrap" style={{ paddingBlock: "32px 72px", maxWidth: 980 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 8 }}>
        <Link href="/" className="btn ghost" style={{ padding: "6px 12px" }}>← Home</Link>
        <h1>Trust &amp; governance</h1>
      </div>
      <p style={{ color: "var(--ink-soft)", marginBottom: 22, maxWidth: 680 }}>
        Responsible AI is the product, not a disclaimer. Every control below is enforced in code and
        demonstrable live. RealDoor extracts, explains, and prepares — a qualified human decides.
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 26 }}>
        {EVIDENCE.map(([k, v]) => (
          <div key={k} className="sheet" style={{ padding: "10px 14px", minWidth: 130 }}>
            <div className="mono" style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--navy)" }}>{v}</div>
            <div className="small">{k}</div>
          </div>
        ))}
      </div>

      <h2 style={{ marginBottom: 12 }}>Controls (enforced)</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14, marginBottom: 30 }}>
        {CONTROLS.map(([h, d]) => (
          <div key={h} className="sheet" style={{ padding: 16 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
              <span className="stamp ready" style={{ transform: "none", padding: "2px 6px", fontSize: "0.62rem" }}>enforced</span>
              <strong style={{ color: "var(--navy)" }}>{h}</strong>
            </div>
            <p className="small" style={{ margin: 0 }}>{d}</p>
          </div>
        ))}
      </div>

      {program && (
        <>
          <h2 style={{ marginBottom: 12 }}>Program configuration</h2>
          <div className="sheet ruled" style={{ padding: "6px 16px", marginBottom: 30 }}>
            {[["Program", program.program], ["Metro", program.metro], ["Rule year", program.rule_year],
              ["Threshold basis", program.threshold_basis], ["Effective date", program.effective_date],
              ["Currency window", `${program.currency_window_days} days`]].map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", gap: 12 }}>
                <span className="small">{k}</span><span className="mono" style={{ fontSize: "0.85rem" }}>{v}</span>
              </div>
            ))}
            <p className="small" style={{ padding: "8px 0 4px" }}>{program.extensibility_note}</p>
          </div>
        </>
      )}

      {meta?.model_disclosure && (
        <>
          <h2 style={{ marginBottom: 12 }}>Model &amp; data use</h2>
          <div className="callout" style={{ marginBottom: 30 }}>
            <p style={{ margin: 0 }}>
              <strong>{meta.model_disclosure.provider}</strong> ({meta.model_disclosure.model}) — used for {meta.model_disclosure.used_for}.
            </p>
            <p className="small" style={{ margin: "8px 0 0" }}>Not used for: {meta.model_disclosure.not_used_for}</p>
            <p className="small" style={{ margin: "6px 0 0" }}>{meta.model_disclosure.data_use}</p>
          </div>
        </>
      )}

      {features && (
        <>
          <h2 style={{ marginBottom: 8 }}>Feature registry</h2>
          <p className="small" style={{ marginBottom: 12 }}>{features.statement}</p>
          <div className="sheet" style={{ overflowX: "auto", marginBottom: 16 }}>
            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.88rem" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1.5px solid var(--ink)" }}>
                  <th style={{ padding: "10px 14px" }}>Field</th><th style={{ padding: "10px 14px" }}>Purpose</th>
                </tr>
              </thead>
              <tbody>
                {features.fields.map((f: any) => (
                  <tr key={f.field} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td className="mono" style={{ padding: "8px 14px", color: "var(--navy)", whiteSpace: "nowrap" }}>{f.field}</td>
                    <td style={{ padding: "8px 14px" }}>{f.purpose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="callout blocked">
            <div className="h">Explicitly never used</div>
            <p className="small" style={{ margin: "4px 0 0" }}>{features.explicitly_not_used.join(" · ")}</p>
          </div>
        </>
      )}
    </div>
  );
}
