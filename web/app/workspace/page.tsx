"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  api, downloadUploadPacket, ExtractedDocument, money, Assessment, UploadAuditEvent, usesStatelessUploads,
} from "@/lib/api";
import { Journey } from "@/components/Journey";

type BrowserDocument = { document: ExtractedDocument; imageUrl: string };

function withBrowserPreviews(data: Assessment, documents: BrowserDocument[]): Assessment {
  const previews = new Map(documents.map(({ document, imageUrl }) => [document.document_id, { document, imageUrl }]));
  return {
    ...data,
    documents: data.documents.map((doc) => {
      const preview = previews.get(doc.document_id);
      return preview ? {
        ...doc,
        image_url: preview.imageUrl,
        image_w: preview.document.page_size_points[0] * 2,
        image_h: preview.document.page_size_points[1] * 2,
      } : doc;
    }),
  };
}

export default function Workspace() {
  const router = useRouter();
  const [sid, setSid] = useState<string | null>(null);
  const [stateless, setStateless] = useState(false);
  const [data, setData] = useState<Assessment | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const started = useRef(false);
  const documents = useRef<BrowserDocument[]>([]);
  const overrides = useRef<Record<string, Record<string, any>>>({});
  const audit = useRef<UploadAuditEvent[]>([]);

  const appendAudit = useCallback((action: string, detail: Record<string, string> = {}) => {
    const event = { ts: new Date().toISOString(), action, detail };
    audit.current = [...audit.current, event];
    setData((current) => current ? { ...current, audit: audit.current } : current);
    return audit.current;
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const hosted = usesStatelessUploads();
    setStateless(hosted);
    api.meta().then(setMeta).catch(() => {});
    if (hosted) {
      const initialAudit = [{ ts: new Date().toISOString(), action: "workspace_opened", detail: {} }];
      audit.current = initialAudit;
      api.uploadReassess([], {}, initialAudit)
        .then(setData)
        .catch(() => setErr("Could not start the upload workspace. Is the deployed API reachable?"));
      return;
    }
    api.createSession()
      .then((s) => { setSid(s.session_id); return api.session(s.session_id); })
      .then(setData)
      .catch(() => setErr("Could not start a session. Is the API running on :8000?"));
  }, []);

  const upload = useCallback(async (files: FileList) => {
    setErr(null);
    setBusy(true);
    try {
      let last: Assessment | null = null;
      if (stateless) {
        let nextDocuments = documents.current;
        for (const f of Array.from(files)) {
          const extraction = await api.extractUpload(f);
          nextDocuments = [...nextDocuments, { document: extraction.document, imageUrl: extraction.image_url }];
          documents.current = nextDocuments;
          const nextAudit = appendAudit("document_added", {
            document_id: extraction.document.document_id,
            document_type: extraction.document.document_type,
          });
          last = await api.uploadReassess(nextDocuments.map((doc) => doc.document), overrides.current, nextAudit);
        }
        if (last) setData(withBrowserPreviews(last, documents.current));
      } else {
        if (!sid) return;
        for (const f of Array.from(files)) last = (await api.uploadDoc(sid, f)).assessment;
        if (last) setData(last);
      }
    } catch (e: any) {
      setErr("That upload could not be read. Send a PDF or image (synthetic/test documents only).");
    } finally {
      setBusy(false);
    }
  }, [appendAudit, sid, stateless]);

  const reassess = useCallback(async (nextOverrides: Record<string, Record<string, any>>) => {
    if (!stateless) {
      const assessment = await api.sessionReassess(sid!, nextOverrides);
      setData(assessment);
      return assessment;
    }
    const previous = overrides.current;
    overrides.current = nextOverrides;
    let nextAudit = audit.current;
    for (const [documentId, fields] of Object.entries(nextOverrides)) {
      for (const [field, value] of Object.entries(fields)) {
        if (previous[documentId]?.[field] !== value) {
          nextAudit = appendAudit("field_corrected", { document_id: documentId, field });
        }
      }
    }
    const assessment = await api.uploadReassess(documents.current.map((doc) => doc.document), nextOverrides, nextAudit);
    const withPreviews = withBrowserPreviews(assessment, documents.current);
    setData(withPreviews);
    return withPreviews;
  }, [appendAudit, sid, stateless]);

  const ask = useCallback((question: string) => {
    if (!stateless) return api.sessionAsk(sid!, question);
    const nextAudit = appendAudit("rules_question_asked", {});
    return api.uploadAsk(documents.current.map((doc) => doc.document), overrides.current, nextAudit, question);
  }, [appendAudit, sid, stateless]);

  const confirm = useCallback((documentId: string, field: string) => {
    if (stateless) {
      appendAudit("field_confirmed", { document_id: documentId, field });
      return;
    }
    if (sid) api.confirmField(sid, documentId, field).catch(() => {});
  }, [appendAudit, sid, stateless]);

  const packet = useCallback(async () => {
    if (!stateless) return;
    const nextAudit = appendAudit("packet_exported", {});
    await downloadUploadPacket(documents.current.map((doc) => doc.document), overrides.current, nextAudit);
  }, [appendAudit, stateless]);

  async function del() {
    if (stateless) {
      documents.current = [];
      overrides.current = {};
      audit.current = [];
      router.push("/");
      return;
    }
    if (sid) await api.deleteSession(sid);
    router.push("/");
  }

  return (
    <div className="wrap" style={{ paddingBlock: "24px 72px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
          <Link href="/" className="btn ghost" style={{ padding: "6px 12px" }}>← Home</Link>
          <h1 style={{ fontSize: "1.4rem" }}>Your documents</h1>
          {!stateless && sid && <span className="mono small">session {sid.slice(0, 8)}</span>}
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
            onReassess={reassess}
            onAsk={ask}
            onConfirm={confirm}
            packetHref={stateless ? "" : api.sessionPacket(sid!)}
            onPacket={stateless ? packet : undefined}
            onDelete={del}
            deleteLabel={stateless ? "Clear these documents" : "Delete this session"}
            onUpload={upload}
            busyUpload={busy}
          />
        : <p className="small">Starting a private workspace…</p>}
    </div>
  );
}
