"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, money, Assessment } from "@/lib/api";
import { Journey } from "@/components/Journey";

export default function Workspace() {
  const router = useRouter();
  const [sid, setSid] = useState<string | null>(null);
  const [data, setData] = useState<Assessment | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api.meta().then(setMeta).catch(() => {});
    api.createSession()
      .then((s) => { setSid(s.session_id); return api.session(s.session_id); })
      .then(setData)
      .catch(() => setErr("Could not start a session. Is the API running on :8000?"));
  }, []);

  const upload = useCallback(async (files: FileList) => {
    if (!sid) return;
    setErr(null);
    setBusy(true);
    try {
      let last: Assessment | null = null;
      for (const f of Array.from(files)) last = (await api.uploadDoc(sid, f)).assessment;
      if (last) setData(last);
    } catch (e: any) {
      setErr("That upload could not be read. Send a PDF or image (synthetic/test documents only).");
    } finally {
      setBusy(false);
    }
  }, [sid]);

  async function del() {
    if (sid) await api.deleteSession(sid);
    router.push("/");
  }

  return (
    <div className="wrap" style={{ paddingBlock: "24px 72px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
          <Link href="/" className="btn ghost" style={{ padding: "6px 12px" }}>← Home</Link>
          <h1 style={{ fontSize: "1.4rem" }}>Your documents</h1>
          {sid && <span className="mono small">session {sid.slice(0, 8)}</span>}
        </div>
        {data && (
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span className="mono" style={{ fontSize: "1.05rem" }}>
              {money(data.annualized_income)} <span className="small">vs {money(data.threshold)} (60% AMI)</span>
            </span>
            <span className={`stamp ${data.readiness_status === "READY_TO_REVIEW" ? "ready" : "review"}`}>
              {data.readiness_status === "READY_TO_REVIEW" ? "Ready to review" : "Needs review"}
            </span>
          </div>
        )}
      </div>

      {meta && (
        <p className="small" style={{ marginBottom: 14 }}>
          Extraction by {meta.model_disclosure.provider} ({meta.model_disclosure.model}), used only to read fields.
          {" "}Processed in memory, not stored, not used for training. Synthetic/test documents only.
          {!meta.vision_enabled && <strong style={{ color: "var(--red)" }}> — vision is not configured (set OPENAI_API_KEY).</strong>}
        </p>
      )}
      {err && <div className="callout blocked" style={{ marginBottom: 14 }}><div className="h">Heads up</div>{err}</div>}

      {data
        ? <Journey
            data={data}
            onReassess={(ov) => api.sessionReassess(sid!, ov).then((a) => { setData(a); return a; })}
            onAsk={(q) => api.sessionAsk(sid!, q)}
            onConfirm={(docId, f) => { if (sid) api.confirmField(sid, docId, f).catch(() => {}); }}
            packetHref={api.sessionPacket(sid!)}
            onDelete={del}
            onUpload={upload}
            busyUpload={busy}
          />
        : <p className="small">Starting a private session…</p>}
    </div>
  );
}
