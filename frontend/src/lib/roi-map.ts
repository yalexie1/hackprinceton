export type RoiRow = {
  zip: string;
  lat: number;
  lon: number;
  utility: string;
  rate_usd_per_kwh: number;
  rate_source: "zip_utility" | "state_average";
  annual_kwh: number;
  net_upfront_usd: number;
  annual_savings_usd: number;
  payback_years: number | null;
  basis: string;
};
export type RoiMapData = {
  city: "la" | "houston";
  name: string;
  built: string;
  label: string;
  assumptions: string[];
  rows: RoiRow[];
};

// Short payback is good: green; long is red. Bins are quintiles of the city's own range, so the map shows
// which areas are better than the rest of the same city.
export const ROI_COLORS = ["#1a7f4b", "#6aa84f", "#d6b400", "#e07b00", "#b3261e"];

export function paybackBreaks(rows: RoiRow[]): number[] {
  const v = rows
    .map((r) => r.payback_years)
    .filter((x): x is number => x !== null)
    .sort((a, b) => a - b);
  if (!v.length) return [];
  return [0.2, 0.4, 0.6, 0.8].map((q) => v[Math.min(v.length - 1, Math.floor(q * v.length))]);
}

export function paybackColor(years: number | null, breaks: number[]): string {
  if (years === null) return "#7a7a7a";
  const i = breaks.findIndex((b) => years < b);
  return ROI_COLORS[i === -1 ? ROI_COLORS.length - 1 : i];
}

export function rankedZips(rows: RoiRow[]): RoiRow[] {
  return rows
    .filter((r) => r.payback_years !== null)
    .sort((a, b) => (a.payback_years as number) - (b.payback_years as number));
}
