"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, money, Assessment } from "@/lib/api";
import { Journey } from "@/components/Journey";

export default function HouseholdPage({ params }: { params: { id: string } }) {
  const id = params.id;
  const [data, setData] = useState<Assessment | null>(null);

  useEffect(() => { api.household(id).then(setData); }, [id]);
  if (!data) return <div className="wrap" style={{ padding: 48 }}><p className="small">Loading case file…</p></div>;

  const ready = data.readiness_status === "READY_TO_REVIEW";
  return (
    <div className="wrap" style={{ paddingBlock: "24px 72px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 18 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
          <Link href="/" className="btn ghost" style={{ padding: "6px 12px" }}>← Case files</Link>
          <span className="mono small">{data.household_id}</span>
          <h1 style={{ fontSize: "1.4rem" }}>Household of {data.household_size}</h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span className="mono" style={{ fontSize: "1.05rem" }}>
            {money(data.annualized_income)} <span className="small">vs {money(data.threshold)} (60% AMI)</span>
          </span>
          <span className={`stamp ${ready ? "ready" : "review"}`}>{ready ? "Ready to review" : "Needs review"}</span>
        </div>
      </div>
      <Journey
        data={data}
        onReassess={(ov) => api.reassess(id, ov).then((a) => { setData(a); return a; })}
        onAsk={(q) => api.ask(id, q)}
        packetHref={api.householdPacket(id)}
      />
    </div>
  );
}
