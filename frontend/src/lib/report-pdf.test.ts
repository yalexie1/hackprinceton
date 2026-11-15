import { describe, expect, it } from "vitest";
import { createAuditPdf } from "./report-pdf";
import { demoShowcaseRun } from "./fixtures";
const house = demoShowcaseRun();

describe("PDF report", () => {
  it("creates a paginated PDF with point estimates and source limitations", () => {
    const run = structuredClone(house);
    run.plan!.total_annual_savings_usd.low = -623;
    run.warnings = ["Contractor quote unverified. Confirm before proceeding."];
    const pdf = createAuditPdf(run);
    const output = pdf.output();
    expect(output.startsWith("%PDF-")).toBe(true);
    expect(pdf.getNumberOfPages()).toBeGreaterThan(1);
    for (const text of ["not guarantees", "Building details", "could increase energy bills"]) expect(output).toContain(text);
    expect(output).not.toContain("-$623");
    expect(output).not.toContain("Estimated annual bill savings: $619 (estimated range");
    expect(output).not.toContain("What to check before deciding");
    expect(output).not.toContain("Contractor quote unverified");
    expect(output).not.toContain("wall.u_value");
    expect(output).not.toContain("specs/physics");
    expect(run.plan!.total_annual_savings_usd.low).toBe(-623);
  });
});
