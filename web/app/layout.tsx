import type { Metadata } from "next";
import { Atkinson_Hyperlegible } from "next/font/google";
import "./globals.css";

const atkinson = Atkinson_Hyperlegible({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-atkinson",
  display: "swap",
});

export const metadata: Metadata = {
  title: "RealDoor — Readiness Passport",
  description:
    "A renter-side copilot that turns household documents into a human-confirmed, evidence-linked readiness packet. It never decides eligibility.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={atkinson.variable}>
      <body>
        <a href="#main" className="skip-link">Skip to main content</a>
        <header className="masthead">
          <div className="wrap">
            <div className="brand">
              <span className="logo">RealDoor</span>
              <span className="kicker">Readiness Passport</span>
            </div>
            <span style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
              <a href="/trust" className="edition" style={{ fontWeight: 700, color: "var(--navy)" }}>Trust &amp; governance</a>
              <span className="edition">Boston–Cambridge–Quincy · LIHTC · FY2026 · eff. 2026-05-01</span>
            </span>
          </div>
        </header>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
