import type { RunResult } from "./types";

export class RealAuditRequired extends Error {
  constructor() {
    super(
      "This property doesn’t have a real audit available yet. Try another property or return after its building records have been added.",
    );
    this.name = "RealAuditRequired";
  }
}

// Reject a completed example before reading its replay stream: that stream can
// itself contain made-up savings, so hiding only the final plan is insufficient.
export function requireRealAudit(run: RunResult, sid: string) {
  if (run.property.sid !== sid || run.request.sid !== sid)
    throw new RealAuditRequired();
  if (
    run.data_source === "example" ||
    (run.status !== "running" && run.data_source !== "live")
  )
    throw new RealAuditRequired();
  if (
    [
      ...run.measures,
      ...(run.plan?.selected.map(({ measure }) => measure) || []),
      ...(run.plan?.financeable || []),
    ].some((measure) =>
      /placeholder|illustrative|\bexample\b|\bTBD\b/i.test(
        measure.finance?.cost_source || "",
      ),
    )
  )
    throw new RealAuditRequired();
  return run;
}

export function hasPlaceholderEvidence(value: {
  label?: string;
  value?: unknown;
  evidence?: { ref?: string; note?: string | null }[];
}) {
  return /\bplaceholder\b|\bTBD\b|\bTODO\b|not a sourced/i.test(
    [
      value.label || "",
      typeof value.value === "string" ? value.value : "",
      ...(value.evidence || []).flatMap((item) => [
        item.ref || "",
        item.note || "",
      ]),
    ].join(" "),
  );
}
