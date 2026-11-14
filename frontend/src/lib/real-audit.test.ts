import { describe, expect, it } from "vitest";
import {
  requireRealAudit,
  RealAuditRequired,
  hasPlaceholderEvidence,
} from "./real-audit";
import type { RunResult } from "./types";
import house from "../../../specs/examples/house/run_result.json";

const real = () =>
  ({
    ...structuredClone(house),
    data_source: "live",
    served_by: "replay",
  }) as RunResult;
describe("real property results only", () => {
  it("accepts both saved real audits and fresh calculations", () => {
    for (const served_by of ["replay", "analysis", "live"] as const) {
      const run = real();
      run.served_by = served_by;
      expect(requireRealAudit(run, run.property.sid)).toBe(run);
    }
  });
  it("rejects example and unknown-source results before their replay stream can be shown", () => {
    for (const data_source of ["example", null, undefined] as const) {
      const run = real();
      run.data_source = data_source;
      expect(() => requireRealAudit(run, run.property.sid)).toThrow(
        RealAuditRequired,
      );
    }
  });
  it("rejects results for the wrong property and explicitly fabricated prices", () => {
    const run = real();
    expect(() => requireRealAudit(run, "another-property")).toThrow(
      RealAuditRequired,
    );
    run.plan!.selected[0].measure.finance!.cost_source =
      "Illustrative placeholder cost";
    expect(() => requireRealAudit(run, run.property.sid)).toThrow(
      RealAuditRequired,
    );
  });
  it("allows a pending audit but blocks explicitly example-based pending data", () => {
    const run = real();
    run.status = "running";
    run.data_source = null;
    expect(requireRealAudit(run, run.property.sid)).toBe(run);
    run.data_source = "example";
    expect(() => requireRealAudit(run, run.property.sid)).toThrow(
      RealAuditRequired,
    );
  });
  it("distinguishes an unsourced placeholder from a legitimate published estimate", () => {
    expect(
      hasPlaceholderEvidence({
        evidence: [{ note: "placeholder: not a sourced density" }],
      }),
    ).toBe(true);
    expect(
      hasPlaceholderEvidence({
        label: "Wall insulation",
        evidence: [
          { note: "Estimated from building age using a published reference" },
        ],
      }),
    ).toBe(false);
  });
});
