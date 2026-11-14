import type { PropertySummary } from "./types";

// Reviewed live-data readiness order agreed by the analysis/data owners on Message Board #1.
// This is an evidence inventory, not a probability, savings forecast or financial ranking.
const readiness = {
  zvKHR9DHNjJ: {
    order: 1,
    label: "Most measured inputs",
    evidence: "Measured walls, window openings and room outlines.",
    limitation: "Utility bills and contractor pricing still need verification.",
  },
  ZSPaQbkGcJJ: {
    order: 2,
    label: "More estimated inputs",
    evidence:
      "339 scan views. Walls use the aerial footprint; windows are estimated from images.",
    limitation: "The live scan has no measured wall graph or room outlines.",
  },
  L3266YcPPvd: {
    order: 3,
    label: "More estimated inputs",
    evidence:
      "88 scan views. Walls use the aerial footprint; windows are estimated from images.",
    limitation:
      "The live scan has no measured wall graph or room outlines. Check the audit’s weather-source note.",
  },
} as const;

export function propertyReadiness(sid: string) {
  return readiness[sid as keyof typeof readiness] || null;
}

export function sortByReadiness(properties: PropertySummary[]) {
  return [...properties].sort(
    (a, b) =>
      (propertyReadiness(a.sid)?.order ?? Number.MAX_SAFE_INTEGER) -
      (propertyReadiness(b.sid)?.order ?? Number.MAX_SAFE_INTEGER),
  );
}
