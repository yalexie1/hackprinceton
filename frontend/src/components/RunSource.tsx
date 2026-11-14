import type { RunResult } from "../lib/types";

export default function RunSource({ run }: { run: RunResult }) {
  const source = run.data_source;
  const delivery = run.served_by;
  return (
    <section
      className={`run-source source-${source || "unknown"}`}
      aria-label="Run data source"
    >
      <div className="run-source-labels">
        <strong>
          {source === "live"
            ? "Live property data"
            : source === "example"
              ? "Example property data"
              : "Property data source unknown"}
        </strong>
        <span>
          {delivery === "replay"
            ? "Saved replay"
            : delivery === "live"
              ? "Live run"
              : "Delivery mode unknown"}
        </span>
      </div>
      <p>
        {source === "example"
          ? "This analysis uses example property inputs."
          : source === "live"
            ? delivery === "replay"
              ? "A recorded analysis of live property data. Viewing it does not run a fresh analysis."
              : "This analysis uses live property data, as reported by the analysis service."
            : "Property-data provenance has not been reported for this run."}
      </p>
    </section>
  );
}
