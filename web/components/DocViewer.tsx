"use client";
import { Doc } from "@/lib/api";

export function DocViewer({
  doc,
  activeField,
  onField,
}: {
  doc: Doc;
  activeField: string | null;
  onField: (f: string | null) => void;
}) {
  const pct = (v: number, total: number) => `${(v / total) * 100}%`;
  return (
    <div className="docstage" style={{ width: "100%" }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={doc.image_url} alt={`${doc.document_label} for ${doc.document_id}`} />
      {doc.fields.map((f) => {
        const [x0, y0, x1, y1] = f.box_px;
        return (
          <div
            key={f.field}
            className={`srcbox ${activeField === f.field ? "active" : ""}`}
            style={{
              left: pct(x0, doc.image_w),
              top: pct(y0, doc.image_h),
              width: pct(x1 - x0, doc.image_w),
              height: pct(y1 - y0, doc.image_h),
              pointerEvents: "auto",
              cursor: "pointer",
            }}
            onMouseEnter={() => onField(f.field)}
            onMouseLeave={() => onField(null)}
            aria-hidden
          />
        );
      })}
      {doc.injection.present && (
        <div
          className="srcbox injection"
          style={{ left: "6%", bottom: "6%", right: "6%", height: "8%" }}
          aria-hidden
        />
      )}
    </div>
  );
}
