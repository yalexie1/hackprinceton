import { describe, expect, it } from "vitest";
import { auditEventText, evidenceText, inputName, readableText, warningText } from "./homeowner-language";

describe("homeowner wording", () => {
  it("names an audit operation without leaking its function name", () => {
    const result = auditEventText({type:"tool_call",stage:"S3",message:"detect_roof_elements",payload:{}});
    expect(result).toContain("roof outline");
    expect(result).not.toContain("detect_roof_elements");
  });
  it("explains the real outline disagreement, keeping its numbers and date", () => {
    const result = warningText("vexcel property/extract:structure (fallback): 5 candidate structure(s) over the CoStar address point across 5 capture(s); chose 191 m2 from us-ca-glendale-2025 (2025-12-09), 26% from the 151 m2 CoStar floor plate; 4 other capture(s) of it were within 10% and lost on date");
    for (const value of ["191 m²","151 m²","26%","2025-12-09"]) expect(result).toContain(value);
    expect(result).not.toContain("property/extract");
    expect(result).toContain("Confirm");
  });
  it("retains negative bounds and uncertainty while translating identifiers", () => {
    const result = readableText("ENV_WALL: NPV -$823 to $533, unverified; see specs/physics/02-thermal-systems.md. wall.u_value needs checking.");
    for (const fact of ["-$823", "$533", "unverified", "needs checking"]) expect(result).toContain(fact);
    for (const token of ["ENV_WALL", "NPV", "specs/", "wall.u_value"]) expect(result).not.toContain(token);
  });
  it("shows the source and observation without an opaque scan id", () => {
    const result = evidenceText({kind:"pano",ref:"private-opaque-id",note:"Panel not visible; two_prong outlets uncertain."});
    expect(result).toContain("Interior photographs");
    expect(result).toContain("Panel not visible");
    expect(result).toContain("uncertain");
    expect(result).not.toContain("private-opaque-id");
    expect(inputName("window.shgc")).toContain("Sunlight heat");
  });
  it("does not corrupt words containing a short categorical value", () => {
    expect(readableText("Las Vegas has gas service.")).toBe("Las Vegas has gas service.");
  });
  it("names the tariff sector the property actually uses, never 'homes' for an office", () => {
    const office = warningText("tariff eia/retail-sales (fallback): EIA state average retail price, CA COM, 2026-08");
    expect(office).toContain("state average for businesses");
    expect(office).not.toContain("for homes");
    expect(office).toContain("2026-08");
    const home = warningText("tariff eia/retail-sales (fallback): EIA state average retail price, CA RES, 2026-08");
    expect(home).toContain("state average for homes");
    const gas = warningText("tariff eia/natural-gas-price (fallback): EIA state average delivered gas price, TX COM, 2025");
    expect(gas).toContain("delivered price for businesses");
    const unknown = warningText("tariff eia/retail-sales (fallback): EIA state average retail price, 2026-08");
    expect(unknown).not.toMatch(/for (homes|businesses)/);
  });
});
