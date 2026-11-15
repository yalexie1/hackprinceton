import { Info } from "lucide-react";
import DocumentText from "./DocumentText";

function noteHeading(note: string) {
  if (/weather|climate|TMY/i.test(note)) return "Review the weather data used";
  if (/tariff|EIA|energy price/i.test(note))
    return "Check the energy prices used";
  if (/vexcel|matterport|footprint|wall graph|geometry/i.test(note))
    return "Some building measurements need checking";
  if (/budget|re-run|replan/i.test(note))
    return "Check that the plan matches your budget";
  if (/cost|price|quote/i.test(note))
    return "Confirm the cost with a contractor";
  return "A detail in this audit needs checking";
}

export default function Warnings({ warnings }: { warnings: string[] }) {
  const unique = [...new Set(warnings.filter(Boolean))];
  if (!unique.length) return null;
  const groups = new Map<string, string[]>();
  for (const warning of unique) {
    const heading = noteHeading(warning);
    groups.set(heading, [...(groups.get(heading) || []), warning]);
  }
  return (
    <section
      className="run-warnings"
      aria-label="Audit warnings and data quality"
    >
      <h3>What to check before deciding</h3>
      {[...groups].map(([heading, notes]) => (
        <details className="warning-detail" key={heading}>
          <summary>
            <Info size={18} />
            {heading} <span>{notes.length > 1 ? `Read ${notes.length} notes` : "Read full note"}</span>
          </summary>
          {notes.map((note) => <p key={note}>{note}</p>)}
        </details>
      ))}
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
  const fallback =
    "Read the selected measures and their evidence before you start work.";
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
        Every input behind these numbers is in the Assumptions tab, with where
        it came from.
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
