import { describe, expect, it } from "vitest";
import { MEASURE_NAMES, REASON_DETAIL, REASON_LABELS, measureName } from "./FindingReason";

describe("measureName", () => {
  it("prefers the title the result carried", () => {
    expect(measureName("WIN_FILM", "Solar film, 3M series")).toBe("Solar film, 3M series");
  });

  it("falls back to a readable name so a reader never meets a raw id", () => {
    expect(measureName("WIN_FILM")).toBe("Solar control window film");
    expect(measureName("HVAC_RTU")).toBe("High-efficiency rooftop units");
  });

  it("tidies an id it has never seen rather than printing it raw", () => {
    expect(measureName("SOME_NEW_MEASURE")).toBe("Some new measure");
  });
});

describe("the reason tables", () => {
  it("explains every reason the contract allows", () => {
    // SkippedItem.reason is a closed set in the contract; a reason with no explanation would
    // open to "no further explanation is recorded", which is worse than useless on stage.
    const reasons = [
      "over_budget", "role", "feasibility", "no_savings", "not_cost_effective",
      "already_done", "no_cost_data",
    ];
    for (const reason of reasons) {
      expect(REASON_LABELS[reason], reason).toBeTruthy();
      expect(REASON_DETAIL[reason]?.what, reason).toBeTruthy();
      expect(REASON_DETAIL[reason]?.change, reason).toBeTruthy();
    }
  });

  it("introduces the savings-to-investment test in words, not as an acronym", () => {
    const what = REASON_DETAIL.not_cost_effective.what;
    expect(what).toContain("savings-to-investment ratio");
    expect(what).not.toMatch(/\bSIR\b/);
  });

  it("names every measure id the contract allows", () => {
    const ids = [
      "ENV_ATTIC", "ENV_WALL", "ENV_AIRSEAL", "WIN_REPLACE", "WIN_FILM", "WIN_SHADE",
      "ROOF_COOL", "HVAC_HP", "HVAC_RTU", "HVAC_ECON", "HVAC_DUCT", "DHW_HPWH",
      "LGT_LED", "LGT_CTRL", "PLUG_MGMT", "CTRL_TSTAT", "PV_ROOF", "LAYOUT",
    ];
    for (const id of ids) expect(MEASURE_NAMES[id], id).toBeTruthy();
  });
});
