import type { RunResult } from "../lib/types";

export default function RunSource({ run }: { run: RunResult }) {
  const source = run.data_source;
  const delivery = run.served_by;
  if (run.status === "running" && source !== "live")
    return (
      <p className="inline-note">Checking this property’s building records…</p>
    );
  return (
    <section
      className={`run-source source-${source || "unknown"}`}
      aria-label="Run data source"
    >
      <div className="run-source-labels">
        <strong>
          {source === "live"
            ? "Based on this property’s records"
            : source === "example"
              ? "Example inputs — not a real property audit"
              : "Building records not verified"}
        </strong>
        <span>
          {delivery === "replay"
            ? "Saved property audit"
            : delivery === "analysis"
              ? "New calculation"
              : delivery === "live"
                ? "New audit"
                : "Audit type not reported"}
        </span>
      </div>
      <p>
        {source === "example"
          ? "This analysis uses example property inputs."
          : source === "live"
            ? delivery === "replay"
              ? "This is a saved audit of the property’s records. Viewing it does not run a fresh analysis."
              : delivery === "analysis"
                ? "Calculated using this property’s records, your budget and your role."
                : "This audit uses the available records for this property."
            : "The source of this audit’s building records has not been confirmed."}
      </p>
    </section>
  );
}
