import { Info } from "lucide-react";
import DocumentText from "./DocumentText";

export default function Warnings({ warnings }: { warnings: string[] }) {
  const unique = [...new Set(warnings.filter(Boolean))];
  if (!unique.length) return null;
  return (
    <section
      className="run-warnings"
      aria-label="Audit warnings and data quality"
    >
      <h3>Notes &amp; data quality</h3>
      {unique.map((warning) =>
        warning.length > 150 ? (
          <details className="warning-detail" key={warning}>
            <summary>
              <Info size={18} />
              {warning.slice(0, 120)}… <span>Read full note</span>
            </summary>
            <p>{warning}</p>
          </details>
        ) : (
          <p key={warning}>
            <Info size={18} />
            <span>{warning}</span>
          </p>
        ),
      )}
    </section>
  );
}

/**
 * The first paragraph that says something, and the rest of the report.
 *
 * The report is 2,800 to 3,000 characters across seven to nine paragraphs. On the plan page a
 * reader wants the short version; the detail belongs where they go looking for it. The split is
 * on the report's own paragraphs, and not one word is rewritten - the numbers in it are the
 * backend's, and the specs are the record.
 */
export function splitNarrative(text: string): { lead: string; rest: string } {
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim());
  const first = paragraphs.findIndex((p) => !p.trim().startsWith("#"));
  if (first < 0) return { lead: text, rest: "" };
  return {
    lead: paragraphs.slice(0, first + 1).join("\n\n"),
    rest: paragraphs.slice(first + 1).join("\n\n"),
  };
}

export function AuditNarrative({
  text,
  warnings,
  concise = false,
}: {
  text: string;
  warnings: string[];
  concise?: boolean;
}) {
  const fallback = "Read the selected measures and their evidence before you start work.";
  const { lead, rest } = splitNarrative(text || fallback);
  const content = concise ? (
    <>
      <DocumentText variant="report" text={lead} />
      {rest && (
        <details className="narrative-rest">
          <summary>Read the rest of the report</summary>
          <DocumentText variant="report" text={rest} />
        </details>
      )}
      <p className="fineprint">
        Every input behind these numbers is in the Assumptions tab, with where it came from.
      </p>
    </>
  ) : (
    <DocumentText variant="report" text={text || fallback} />
  );
  return warnings.some((warning) => warning.startsWith("re-run:")) ? (
    <>
      <p className="inline-note">
        The plan has changed. This earlier report may contain outdated numbers;
        use the current plan totals.
      </p>
      <details>
        <summary>Read the earlier report</summary>
        {content}
      </details>
    </>
  ) : (
    content
  );
}
