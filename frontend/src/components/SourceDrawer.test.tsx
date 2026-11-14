import { describe, expect, it } from "vitest";
import { groupFormulas, specFor } from "./SourceDrawer";

describe("specFor", () => {
  it("routes each physics prefix to the document that holds it", () => {
    expect(specFor("PV-10")).toContain("01-solar-pv");
    expect(specFor("BEN-03")).toContain("02-thermal-systems");
    expect(specFor("LCT-01")).toContain("03-daylight-comfort");
    expect(specFor("VAL-01")).toContain("04-economics");
  });

  it("returns null for an id it does not recognise, rather than guessing a document", () => {
    // Pointing a reader at the wrong spec is worse than admitting the id is unattributed.
    expect(specFor("XYZ-01")).toBeNull();
    expect(specFor("")).toBeNull();
  });
});

describe("groupFormulas", () => {
  it("gives one line per document, keeping the backend's order within it", () => {
    const groups = groupFormulas(["PV-01", "COST-01", "PV-02", "ECO-07"]);
    expect(groups).toHaveLength(2);
    expect(groups[0].ids).toEqual(["PV-01", "PV-02"]);
    expect(groups[1].ids).toEqual(["COST-01", "ECO-07"]);
  });

  it("collects unrecognised ids under 'unattributed' instead of dropping them", () => {
    const groups = groupFormulas(["PV-01", "XYZ-9"]);
    expect(groups.find((g) => g.spec === "unattributed")?.ids).toEqual(["XYZ-9"]);
  });

  it("is empty for a measure with no recorded formulas", () => {
    expect(groupFormulas([])).toEqual([]);
  });
});
