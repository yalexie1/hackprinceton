import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RoiTable from "./RoiTable";
import { paybackBreaks, paybackColor, rankedZips, ROI_COLORS, type RoiRow } from "../lib/roi-map";

const row = (zip: string, payback: number | null): RoiRow => ({
  zip,
  lat: 34,
  lon: -118,
  utility: "U",
  rate_usd_per_kwh: 0.3,
  rate_source: "zip_utility",
  annual_kwh: 9000,
  net_upfront_usd: 25200,
  annual_savings_usd: 1900,
  payback_years: payback,
  basis: "estimate for a typical home, not an audit",
});
const rows = [row("90003", 12), row("90001", 8), row("90002", 10), row("90004", null), row("90005", 14), row("90006", 9)];

describe("ROI map helpers", () => {
  it("ranks the quickest payback first and leaves out zips with none", () => {
    expect(rankedZips(rows).map((r) => r.zip)).toEqual(["90001", "90006", "90002", "90003", "90005"]);
  });
  it("colours short paybacks green and long ones red, grey when there is none", () => {
    const b = paybackBreaks(rows);
    expect(b).toEqual([10, 12, 15, 20]);                 // the same bands for every city
    expect(paybackColor(8, b)).toBe(ROI_COLORS[0]);
    expect(paybackColor(25, b)).toBe(ROI_COLORS[4]);
    expect(paybackColor(99, b)).toBe(ROI_COLORS[4]);
    expect(paybackColor(null, b)).toBe("#7a7a7a");
  });
  it("renders the ranked table in plain words", () => {
    const html = renderToStaticMarkup(<RoiTable rows={rows} limit={2} />);
    expect(html).toContain("8 years");
    expect(html).toContain("$25,200");
    expect(html).not.toContain("90005");
  });
});
