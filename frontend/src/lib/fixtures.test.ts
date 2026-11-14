import { describe, expect, it } from "vitest";
import { demoBudgets, demoEvents, demoProperties, demoRun } from "./fixtures";
import { polygon } from "./format";
import { resolveSweep } from "../components/Tour";
describe("demo fixtures", () => {
  it("keeps every uncertainty range ordered, including negative net present values", () => {
    function check(value: unknown) {
      if (Array.isArray(value)) value.forEach(check);
      else if (value && typeof value === "object") {
        const record = value as Record<string, unknown>;
        if (
          typeof record.low === "number" &&
          typeof record.expected === "number" &&
          typeof record.high === "number"
        ) {
          expect(record.low).toBeLessThanOrEqual(record.expected);
          expect(record.expected).toBeLessThanOrEqual(record.high);
        }
        Object.values(record).forEach(check);
      }
    }
    for (const p of demoProperties)
      for (const budget of demoBudgets(p.sid)) check(demoRun(p.sid, budget));
  });
  it("provides house and office plans for every saved budget without exceeding the expected cash cap", () => {
    expect(new Set(demoProperties.map((p) => p.segment))).toEqual(
      new Set(["residential", "commercial"]),
    );
    for (const p of demoProperties)
      for (const budget of demoBudgets(p.sid)) {
        const run = demoRun(p.sid, budget);
        const plan = run.plan!;
        expect(plan.total_upfront_usd.expected).toBeLessThanOrEqual(budget);
        expect(
          plan.selected.reduce(
            (total, i) => total + i.measure.finance!.net_upfront_usd.expected,
            0,
          ),
        ).toBeCloseTo(plan.total_upfront_usd.expected, 2);
        expect(
          plan.selected.reduce(
            (total, i) =>
              total + i.measure.finance!.annual_savings_usd.expected,
            0,
          ),
        ).toBeCloseTo(plan.total_annual_savings_usd.expected, 2);
        if (
          plan.selected.some(
            (item) => item.measure.finance!.net_upfront_usd.expected === 0,
          )
        )
          expect(
            plan.selected[0].measure.finance!.net_upfront_usd.expected,
          ).toBe(0);
        expect(run.schema_version).toBe("0.2.0");
        expect(run.warnings.join(" ")).toMatch(/illustrative/i);
      }
  });
  it("loads the shared golden house and office with their actual event and request shapes", () => {
    const house = demoRun("zvKHR9DHNjJ", 14000);
    const office = demoRun("HjEyXryhRLk", 3500);
    expect(office.request.role).toBe("landlord");
    expect(office.plan!.value_uplift).toBeTruthy();
    expect(house.property.costar_listing_id).toBe("235967170");
    const event = demoEvents(house.property.sid).find(
      (e) => e.type === "question",
    )!;
    expect(event.payload.question).toEqual(house.questions[0]);
  });
  it("rejects custom demo budgets instead of inventing an analysis result", () => {
    expect(() => demoRun("demo-house", 12345)).toThrow("saved demo budgets");
  });
  it("returns independent snapshots so answering or editing cannot mutate other runs", () => {
    const run = demoRun("demo-house", 15000);
    run.plan!.selected.length = 0;
    expect(demoRun("demo-house", 15000).plan!.selected.length).toBeGreaterThan(
      0,
    );
  });
});
describe("geometry and evidence mapping", () => {
  it("reads georeferenced WKT and rejects invalid or unsupported geometry", () => {
    expect(
      polygon("POLYGON ((-118.1 34.1, -118 34.1, -118 34.2, -118.1 34.1))"),
    ).toHaveLength(4);
    expect(polygon("POLYGON ((NaN 0, 1 0, 1 1, NaN 0))")).toEqual([]);
    expect(polygon("MULTIPOLYGON (((0 0,1 0,1 1,0 0)))")).toEqual([]);
  });
  it("only navigates to a sweep after matching a published sid or uuid", () => {
    const sweeps = { a: { sid: "sdk-a", uuid: "model-pano" } };
    expect(
      resolveSweep({ label: "Insulation", pano_id: "model-pano" }, sweeps),
    ).toBe("sdk-a");
    expect(
      resolveSweep({ label: "Insulation", pano_id: "missing-pano" }, sweeps),
    ).toBeUndefined();
  });
});
