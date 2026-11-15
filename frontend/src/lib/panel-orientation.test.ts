import { describe, expect, it } from "vitest";
import { compassName, panelFacing } from "./panel-orientation";
import type { RunResult } from "./types";

function run(planes: [string, number][], panels: string[]): RunResult {
  return {
    measures: [{ solar: { panels: panels.map((plane_id) => ({ plane_id })) } }],
    building_model: {
      roof_planes: planes.map(([id, azimuth_deg]) => ({ id, azimuth_deg })),
    },
  } as unknown as RunResult;
}

describe("panelFacing", () => {
  it("reads the azimuth of the plane with the most panels", () => {
    const r = run(
      [["plane_east", 90], ["plane_west", 270]],
      ["plane_west", "plane_west", "plane_east"],
    );
    expect(panelFacing(r)).toEqual({ azimuthDeg: 270, label: "west" });
  });
  it("returns null without panels or planes", () => {
    expect(panelFacing(null)).toBeNull();
    expect(panelFacing(run([["plane_south", 176.4]], []))).toBeNull();
    expect(panelFacing(run([], ["plane_south"]))).toBeNull();
  });
  it("names compass points", () => {
    expect(compassName(176.4)).toBe("south");
    expect(compassName(-90)).toBe("west");
    expect(compassName(250)).toBe("west");
    expect(compassName(225)).toBe("southwest");
  });
});
