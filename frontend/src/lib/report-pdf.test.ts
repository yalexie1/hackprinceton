import { describe, expect, it } from "vitest";
import { createAuditPdf } from "./report-pdf";
import { demoShowcaseRun } from "./fixtures";
const house = demoShowcaseRun();

describe("PDF report", () => {
  it("creates paginated PDF content with original ranges and source limitations", () => {
    const run = structuredClone(house);
    run.plan!.total_annual_savings_usd.low = -623;
    run.warnings = ["Contractor quote unverified. Confirm before proceeding."];
    const pdf = createAuditPdf(run);
    const output = pdf.output();
    expect(output.startsWith("%PDF-")).toBe(true);
    expect(pdf.getNumberOfPages()).toBeGreaterThan(1);
    for (const text of ["-$623", "not guarantees", "unverified", "What to check", "Building details"]) expect(output).toContain(text);
    expect(output).not.toContain("wall.u_value");
    expect(output).not.toContain("specs/physics");
    expect(run.plan!.total_annual_savings_usd.low).toBe(-623);
  });
});
