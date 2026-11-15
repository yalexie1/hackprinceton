import { describe, expect, it } from "vitest";
import { auditProgress } from "./AuditProgress";
import type { RunEvent } from "../lib/types";

const ev = (stage: string, type: RunEvent["type"]): RunEvent =>
  ({ type, stage, message: "", payload: {} }) as RunEvent;

describe("auditProgress", () => {
  it("counts the stages that finished, not the events", () => {
    const p = auditProgress(
      [ev("S1", "stage_started"), ev("S1", "stage_done"), ev("S2", "stage_started"),
       ev("S2", "tool_call"), ev("S2", "stage_done"), ev("S3", "stage_started")],
      false,
    );
    expect(p.complete).toBe(2);
    expect(p.total).toBe(8);
    expect(p.label).toBe("Reviewing building images");
  });

  it("reports the last stage reached, so a long stage does not look stalled at the previous one", () => {
    expect(auditProgress([ev("S1", "stage_done"), ev("S5", "stage_started")], false).label)
      .toBe("Baseline");
  });

  it("is complete when the run is done, whatever the stream contained", () => {
    // A run can skip stages (no desks to score, no document to draft), so a finished run must
    // read as finished rather than stalling at 6 of 8.
    const p = auditProgress([ev("S1", "stage_done")], true);
    expect(p.complete).toBe(p.total);
    expect(p.label).toBe("Complete");
  });

  it("ignores events with no stage or an unknown one rather than mislabelling them", () => {
    const p = auditProgress(
      [{ type: "tool_call", message: "", payload: {} } as RunEvent, ev("S99", "stage_done")],
      false,
    );
    expect(p.complete).toBe(0);
    expect(p.label).toBe("Starting");
  });
});
