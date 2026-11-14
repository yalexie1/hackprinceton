import { describe, expect, it } from "vitest";
import { energyPart, energyUpgrades } from "./energy-explorer";
import { demoShowcaseRun } from "./fixtures";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { UpgradeDetails } from "../components/EnergyOverlay";

describe("energy exploration", () => {
  it("keeps not-cost-effective evaluations out of the opportunity highlights", () => {
    const run = demoShowcaseRun();
    const measure = run.measures.find(
      (item) => item.measure_id === "ENV_ATTIC",
    )!;
    run.plan!.selected = run.plan!.selected.filter(
      (item) => item.measure.measure_id !== measure.measure_id,
    );
    run.plan!.skipped = [
      {
        measure_id: measure.measure_id,
        reason: "not_cost_effective",
        detail: "Not cost-effective: SIR 0.74",
      },
    ];
    expect(
      energyUpgrades(run).find(
        (item) => item.measure.measure_id === measure.measure_id,
      ),
    ).toMatchObject({
      status: "unavailable",
      reason: "Not cost-effective: SIR 0.74",
    });
  });
  it("uses marginal savings from the selected plan and preserves input data", () => {
    const run = demoShowcaseRun();
    const selected = run.plan!.selected[0].measure;
    const standalone = run.measures.find(
      (m) => m.measure_id === selected.measure_id,
    )!;
    standalone.finance!.annual_savings_usd.expected = 1;
    const before = JSON.stringify(run);
    const upgrade = energyUpgrades(run).find(
      (u) => u.measure.measure_id === selected.measure_id,
    )!;
    expect(upgrade.status).toBe("planned");
    expect(upgrade.measure.finance!.annual_savings_usd.expected).toBe(
      selected.finance!.annual_savings_usd.expected,
    );
    expect(JSON.stringify(run)).toBe(before);
  });
  it("keeps infeasible and unsourced changes out of the proposed plan", () => {
    const run = demoShowcaseRun();
    const upgrades = energyUpgrades(run);
    expect(
      upgrades
        .filter((u) => u.status === "planned")
        .map((u) => u.measure.measure_id)
        .sort(),
    ).toEqual(run.plan!.selected.map((i) => i.measure.measure_id).sort());
    for (const item of run.plan!.skipped.filter((s) =>
      ["feasibility", "no_cost_data", "no_savings", "already_done"].includes(
        s.reason,
      ),
    )) {
      const upgrade = upgrades.find(
        (u) => u.measure.measure_id === item.measure_id,
      );
      if (upgrade) {
        expect(upgrade.status).toBe("unavailable");
        expect(upgrade.reason).toBe(item.detail);
      }
    }
    expect(
      upgrades.find((u) => u.measure.measure_id === "ENV_ATTIC")!.status,
    ).toBe("opportunity");
  });
  it("does not invent an upgrade when no plan or mapping exists", () => {
    expect(energyUpgrades()).toEqual([]);
    expect(energyPart("FUTURE_MEASURE")).toBeUndefined();
    expect(energyPart("PV_ROOF")).toBe("solar");
    expect(energyPart("HVAC_HP")).toBe("hvac");
  });
  it("shows unavailable findings as reasons rather than positive savings claims", () => {
    const upgrade = energyUpgrades(demoShowcaseRun()).find(
      (u) => u.status === "unavailable",
    )!;
    const html = renderToStaticMarkup(
      React.createElement(UpgradeDetails, { upgrade, onClose: () => {} }),
    );
    expect(html).toContain("NOT INCLUDED");
    expect(html).not.toContain("Estimated annual savings");
    expect(html).toContain("Not added to your plan");
  });
});
