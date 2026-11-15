import { describe, expect, it } from "vitest";
import { homeownerReport, splitNarrative } from "./Warnings";

const REPORT = `## Audit summary

Baseline for the third-floor suite: 308,797 kWh of electricity a year.

The plan follows a consultant's loading order: operations first.

Solar comes last and is shrunk to the budget that is left.`;

describe("splitNarrative", () => {
  it("leads with the first paragraph that says something, not the heading", () => {
    const { lead, rest } = splitNarrative(REPORT);
    expect(lead).toContain("## Audit summary");
    expect(lead).toContain("308,797");
    expect(lead).not.toContain("loading order");
    expect(rest).toContain("loading order");
    expect(rest).toContain("Solar comes last");
  });

  it("changes not one word of the report", () => {
    // The numbers are the backend's. Rewriting them in the view is how a page starts
    // disagreeing with the analysis behind it.
    const { lead, rest } = splitNarrative(REPORT);
    const rejoined = [lead, rest].filter(Boolean).join("\n\n");
    expect(rejoined.replace(/\s+/g, " ")).toBe(REPORT.replace(/\s+/g, " "));
  });

  it("has no hidden rest when the report is one paragraph", () => {
    const { lead, rest } = splitNarrative("Just the one paragraph.");
    expect(lead).toBe("Just the one paragraph.");
    expect(rest).toBe("");
  });

  it("falls back to the whole text when every paragraph is a heading", () => {
    expect(splitNarrative("# One\n\n## Two").lead).toBe("# One\n\n## Two");
  });

  it("handles an empty report without throwing", () => {
    expect(splitNarrative("").lead).toBe("");
  });
});

describe("homeowner report warnings", () => {
  it("turns technical fallback lines into homeowner checks without changing measured figures", () => {
    const report = "Baseline: 7,728 kWh.\n\nWarnings and fallbacks in this run:\n- quaternion sense not decidable from the footprint on this model\n- tariff eia/retail-sales (fallback): EIA state average retail price, CA RES, 2026-08";
    const result = homeownerReport(report);
    expect(result).toContain("7,728 kWh");
    expect(result).toContain("What to check before deciding:");
    expect(result).toContain("Check its orientation");
    expect(result).toContain("state average for homes");
    expect(result).not.toContain("quaternion");
    expect(result).not.toContain("eia/retail-sales");
  });
});
