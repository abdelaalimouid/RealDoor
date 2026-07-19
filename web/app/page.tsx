"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, money, HouseholdSummary } from "@/lib/api";

const SCENARIO: Record<string, string> = {
  "HH-001": "Regular hourly wages",
  "HH-002": "Overtime variance",
  "HH-003": "Wages + benefits",
  "HH-004": "Gig + wages",
  "HH-005": "Expired letter",
  "HH-006": "Near the threshold",
};

export default function Home() {
  const [rows, setRows] = useState<HouseholdSummary[] | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    api.households().then(setRows).catch(() => setErr(true));
  }, []);

  return (
    <div className="wrap" style={{ paddingBlock: "48px 72px" }}>
      <section style={{ maxWidth: 760, marginBottom: 40 }}>
        <p className="chip" style={{ marginBottom: 18 }}>A renter-side copilot · not an eligibility engine</p>
        <h1>
          Turn a shoebox of documents into a packet a caseworker can trust — with
          every number traced back to the page it came from.
        </h1>
        <p style={{ fontSize: "1.12rem", color: "var(--ink-soft)", marginTop: 18, lineHeight: 1.6 }}>
          RealDoor reads a household&apos;s pay stubs and letters, annualizes income by the
          real HUD method, checks it against the frozen FY2026 threshold, and flags what a
          human needs to look at. It shows its work and refuses to decide.
        </p>
        <p style={{ marginTop: 20, fontFamily: "var(--mono)", fontSize: "0.82rem", color: "var(--navy)" }}>
          AI extracts &amp; explains &nbsp;·&nbsp; the renter confirms &nbsp;·&nbsp; a qualified human decides
        </p>
        <div style={{ display: "flex", gap: 12, marginTop: 26, flexWrap: "wrap" }}>
          <Link href="/workspace" className="btn" style={{ fontSize: "1.02rem", padding: "13px 22px" }}>
            Upload your documents →
          </Link>
          {(rows?.length ?? 0) > 0 && (
            <a href="#samples" className="btn ghost" style={{ fontSize: "1.02rem", padding: "13px 22px" }}>
              Or try a sample case
            </a>
          )}
        </div>
        <p className="small" style={{ marginTop: 10 }}>Synthetic/test documents only · processed in memory, never stored.</p>
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 14, margin: "0 0 44px" }}>
        {[["1 · Extract", "Upload a pay stub or letter. RealDoor reads only allowlisted fields and boxes each one on the page."],
          ["2 · Confirm", "You check and correct every value. Nothing is reused until you confirm it — the math updates as you go."],
          ["3 · Prepare", "Cited rules, deterministic income, missing-document flags, and a downloadable packet for a human to review."]].map(([h, d]) => (
          <div key={h} className="sheet" style={{ padding: 16 }}>
            <div className="mono" style={{ color: "var(--navy)", fontWeight: 700, marginBottom: 4 }}>{h}</div>
            <p className="small" style={{ margin: 0 }}>{d}</p>
          </div>
        ))}
      </div>

      {err && (
        <div className="callout blocked"><div className="h">API not reachable</div>
          Start the bridge: <span className="mono">uvicorn api.main:app --port 8000</span> from <span className="mono">realdoor/</span>.
        </div>
      )}

      {(rows?.length ?? 0) > 0 && (
      <div id="samples" style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 16, scrollMarginTop: 20 }}>
        <h2>Sample case files</h2>
        <span className="small">six synthetic households — pick one to walk their readiness journey</span>
      </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 18 }}>
        {(rows ?? []).map((h) => {
          const ready = h.readiness_status === "READY_TO_REVIEW";
          return (
            <Link key={h.household_id} href={`/household/${h.household_id}`}
              className="sheet" style={{ padding: 20, textDecoration: "none", color: "inherit", display: "block" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                <div>
                  <div className="mono" style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>{h.household_id}</div>
                  <div style={{ fontWeight: 700, fontSize: "1.15rem", color: "var(--navy)", marginTop: 2 }}>
                    Household of {h.household_size}
                  </div>
                </div>
                <span className={`stamp ${ready ? "ready" : "review"}`}>{ready ? "Ready" : "Review"}</span>
              </div>
              <p className="chip" style={{ marginTop: 12 }}>{SCENARIO[h.household_id] ?? "Household"}</p>
              <hr className="hairline" style={{ margin: "14px 0" }} />
              <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--mono)", fontSize: "0.95rem" }}>
                <span>{money(h.annualized_income)}</span>
                <span className="small">vs {money(h.threshold)}</span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
