import { Info } from "lucide-react";

export default function Warnings({ warnings }: { warnings: string[] }) {
  const unique = [...new Set(warnings.filter(Boolean))];
  if (!unique.length) return null;
  return (
    <section className="run-warnings" aria-label="Audit warnings and data quality">
      <h3>Notes &amp; data quality</h3>
      {unique.map((warning) =>
        warning.length > 150 ? (
          <details className="warning-detail" key={warning}>
            <summary><Info size={18} />{warning.slice(0, 120)}… <span>Read full note</span></summary>
            <p>{warning}</p>
          </details>
        ) : (
          <p key={warning}><Info size={18} /><span>{warning}</span></p>
        ),
      )}
    </section>
  );
}

export function AuditNarrative({ text, warnings }: { text: string; warnings: string[] }) {
  const content = <p>{text.replace(/^#{1,6}\s+/gm, "") || "Review the selected measures and their evidence before moving ahead."}</p>;
  return warnings.some((warning) => warning.startsWith("re-run:")) ? (
    <>
      <p className="inline-note">The plan has changed. This earlier report may contain outdated numbers; use the current plan totals.</p>
      <details><summary>Read the earlier report</summary>{content}</details>
    </>
  ) : content;
}
