import type { PropertySummary } from "./types";

// Reviewed live-data readiness order agreed by the analysis/data owners on Message Board #1.
// This is an evidence inventory, not a probability, savings forecast or financial ranking.
const readiness = {
  zvKHR9DHNjJ: {
    order: 1,
    label: "More details measured directly",
    evidence: "Measured walls and window openings.",
    limitation:
      "Room shapes still need checking. Add utility bills and confirm a contractor’s price before deciding.",
  },
  ZSPaQbkGcJJ: {
    order: 2,
    label: "Some building details estimated",
    evidence:
      "Walls are estimated from the building’s aerial outline; windows from photos.",
    limitation:
      "Wall sizes and room shapes need checking before detailed design.",
  },
  L3266YcPPvd: {
    order: 3,
    label: "Some building details estimated",
    evidence:
      "Walls are estimated from the building’s aerial outline; windows from photos.",
    limitation:
      "Wall sizes and room shapes need checking. Review the weather data used for the estimate.",
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
