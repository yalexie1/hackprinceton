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

// Short payback is good: green; long is red. The same absolute bands are used for every city, so a colour means the
// same number of years on both maps.
export const ROI_COLORS = ["#1a7f4b", "#6aa84f", "#d6b400", "#e07b00", "#b3261e"];
export const ROI_BREAKS = [10, 12, 15, 20];

export function paybackBreaks(_rows?: RoiRow[]): number[] {
  return ROI_BREAKS;
}

export function paybackColor(years: number | null, breaks: number[] = ROI_BREAKS): string {
  if (years === null) return "#7a7a7a";
  const i = breaks.findIndex((b) => years < b);
  return ROI_COLORS[i === -1 ? ROI_COLORS.length - 1 : i];
}

export function rankedZips(rows: RoiRow[]): RoiRow[] {
  return rows
    .filter((r) => r.payback_years !== null)
    .sort((a, b) => (a.payback_years as number) - (b.payback_years as number));
}
