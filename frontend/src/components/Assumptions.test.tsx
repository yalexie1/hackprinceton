import { describe, expect, it } from "vitest";
import { readableLabel } from "./Assumptions";

describe("readableLabel", () => {
  it("leaves a label the backend already wrote as a sentence", () => {
    expect(readableLabel("Ceiling height", "geometry.ceiling_height_m")).toBe("Ceiling height");
    expect(readableLabel("People working in the suite", "occupancy.count")).toBe(
      "People working in the suite",
    );
  });

  it("humanises a machine key, which is what a user override arrives with", () => {
    // The backend labels almost every input, but an override carries its own key, so the page
    // showed `lighting.lamp_type` to a building owner.
    expect(readableLabel("lighting.lamp_type", "lighting.lamp_type")).toBe("Lighting lamp type");
    expect(readableLabel("wall.u_value", "wall.u_value")).toBe("Wall u value");
  });

  it("falls back to the key when there is no label at all", () => {
    expect(readableLabel("", "hvac.cooling_rating")).toBe("Hvac cooling rating");
  });
});
