import { describe, expect, it } from "vitest";
import { sortByReadiness, propertyReadiness } from "./property-readiness";
import { demoProperties } from "./fixtures";

describe("property evidence readiness", () => {
  it("puts the owner-reviewed measured house ahead of the two estimated office models", () => {
    const shuffled = [...demoProperties].reverse();
    const original = [...shuffled];
    expect(sortByReadiness(shuffled).map((property) => property.sid)).toEqual([
      "zvKHR9DHNjJ",
      "ZSPaQbkGcJJ",
      "L3266YcPPvd",
    ]);
    expect(shuffled).toEqual(original);
  });
  it("keeps unassessed properties last without claiming they have poor data", () => {
    const unknown = { ...demoProperties[0], sid: "not-yet-reviewed" };
    expect(propertyReadiness(unknown.sid)).toBeNull();
    expect(sortByReadiness([unknown, ...demoProperties]).at(-1)).toEqual(
      unknown,
    );
  });
});
