import { readableText, warningText } from "../lib/homeowner-language";
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
        <details open className="warning-detail" key={heading}>
          <summary>
            <Info size={18} />
            {heading} <span>{notes.length > 1 ? `Read ${notes.length} notes` : "Read full note"}</span>
          </summary>
          {notes.map((note) => <p key={note}>{warningText(note)}</p>)}
        </details>
      ))}
    </section>
  );
}

/**
 * The first paragraph that says something, and the rest of the report.
 *
 * The plan page uses the opening summary; individual recommendation cards and
 * the check-before-deciding section provide the detail without repeating the
 * backend's full technical narrative.
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

export function homeownerReport(text: string): string {
  let inChecks = false;
  return text.split("\n").map((line) => {
    if (/^#{1,6}\s+Audit summary \(real analysis\)/i.test(line.trim()))
      return "## Your energy audit";
    if (/^Warnings and fallbacks in this run:\s*$/i.test(line.trim())) {
      inChecks = true;
      return "What to check before deciding:";
    }
    if (inChecks && /^\s*[-*]\s+/.test(line)) {
      return `- ${warningText(line.replace(/^\s*[-*]\s+/, ""))}`;
    }
    if (inChecks && /^#{1,6}\s/.test(line)) inChecks = false;
    return line;
  }).join("\n").replace(/\s*\((?:estimated\s+)?range\s+[^)]*\)/gi, "");
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
    "Review the recommended improvements and confirm the details before you start work.";
  const { lead } = splitNarrative(homeownerReport(text || fallback));
  const content = concise ? (
    <>
      <DocumentText variant="report" text={readableText(lead)} />
      <p className="fineprint">
        Every input behind these numbers is in the Assumptions tab, with where
        it came from.
      </p>
    </>
  ) : (
    <DocumentText variant="report" text={readableText(homeownerReport(text || fallback))} />
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
