import type { MeasureResult, RunResult } from "./types";

export type EnergyPart =
  | "solar"
  | "roof"
  | "attic"
  | "envelope"
  | "windows"
  | "lighting"
  | "hvac"
  | "water"
  | "controls"
  | "workspace";
export type EnergyUpgrade = {
  part: EnergyPart;
  measure: MeasureResult;
  status: "planned" | "opportunity" | "unavailable";
  reason?: string;
};
export type EnergyPoint = {
  part: EnergyPart;
  x: number;
  y: number;
  visible: boolean;
};

export function energyPart(id: string): EnergyPart | undefined {
  if (id === "PV_ROOF") return "solar";
  if (id === "ROOF_COOL") return "roof";
  if (id === "ENV_ATTIC") return "attic";
  if (id.startsWith("ENV_")) return "envelope";
  if (id.startsWith("WIN_")) return "windows";
  if (id.startsWith("LGT_")) return "lighting";
  if (id.startsWith("HVAC_")) return "hvac";
  if (id.startsWith("DHW_")) return "water";
  if (id.startsWith("CTRL_")) return "controls";
  if (id === "LAYOUT") return "workspace";
}

// The selected plan contains marginal results after preceding upgrades. It
// takes precedence over the standalone measure in the evaluation list.
export function energyUpgrades(run?: RunResult | null): EnergyUpgrade[] {
  if (!run?.plan) return [];
  const selected = new Set(
    run.plan.selected.map((item) => item.measure.measure_id),
  );
  const byId = new Map<string, MeasureResult>();
  for (const measure of [
    ...run.measures,
    ...run.plan.financeable,
    ...run.plan.selected.map((item) => item.measure),
  ])
    byId.set(measure.measure_id, measure);
  return [...byId.values()]
    .flatMap((measure) => {
      const part = energyPart(measure.measure_id);
      if (!part) return [];
      const skipped = run.plan!.skipped.find(
        (item) => item.measure_id === measure.measure_id,
      );
      const unavailable =
        !measure.applicable ||
        [
          "feasibility",
          "no_cost_data",
          "already_done",
          "no_savings",
          "role",
        ].includes(skipped?.reason || "");
      return [
        {
          part,
          measure,
          status: selected.has(measure.measure_id)
            ? ("planned" as const)
            : unavailable
              ? ("unavailable" as const)
              : ("opportunity" as const),
          reason: skipped?.detail || measure.not_applicable_reason || undefined,
        },
      ];
    })
    .sort(
      (a, b) => Number(b.status === "planned") - Number(a.status === "planned"),
    );
}
