import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "../App";
import Assumptions from "./Assumptions";
import { FinancingTerms } from "./Plan";
import house from "../../../specs/examples/house/run_result.json";
import type { RunResult } from "../lib/types";

describe("homeowner demo", () => {
  it("never advertises fixture savings or an invented user before a property is chosen", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).not.toContain("$619");
    expect(html).not.toContain("EXAMPLE ENERGY PLAN");
    expect(html).not.toContain("Vinayak Sinha");
    expect(html).not.toContain("Connect API");
    expect(html).toContain("Choose a property below");
    expect(html).toContain("Connecting");
  });
  it("does not display a numeric value for an explicitly unsourced assumption", () => {
    const run = structuredClone(house) as RunResult;
    run.building_model!.assumptions = [
      {
        ...run.building_model!.assumptions[0],
        label: "Lighting density",
        value: { low: 9876, expected: 9876, high: 9876, unit: "W/m²" },
        evidence: [
          {
            kind: "reference",
            ref: "lighting",
            note: "placeholder: not a sourced density",
          },
        ],
      },
    ];
    const html = renderToStaticMarkup(
      <Assumptions run={run} demo={false} busy={false} onSave={() => {}} />,
    );
    expect(html).toContain("Needs confirmation");
    expect(html).not.toContain("9876");
    expect(html).not.toContain("9,876");
    expect(html).not.toContain("placeholder:");
  });
  it("withholds payments when loan terms are incomplete but supports zero-interest loans", () => {
    const scenario = {
      kind: "cpace" as const,
      eligible: true,
      financed_usd: 10000,
      rate: null as number | null,
      term_years: 10,
      annual_payment_usd: 9876,
      net_cashflow_year1_usd: { low: 1, expected: 2, high: 3, unit: "USD" },
      notes: [],
    };
    const missing = renderToStaticMarkup(
      <FinancingTerms scenario={scenario} />,
    );
    expect(missing).toContain("Loan terms still need confirmation");
    expect(missing).not.toContain("9,876");
    const valid = renderToStaticMarkup(
      <FinancingTerms scenario={{ ...scenario, rate: 0 }} />,
    );
    expect(valid).toContain("0% interest");
    expect(valid).toContain("9,876");
  });
});
