import { describe, expect, it } from "vitest";
import {
  UNCAPPED_BUDGET_USD, displayEventMessage, hasBudget, sentinelBinds, visibleWarnings,
} from "./budget-phase";

describe("budget phase", () => {
  it("treats only the sentinel as no budget, including a restored request", () => {
    expect(hasBudget(UNCAPPED_BUDGET_USD)).toBe(false);
    expect(hasBudget(0)).toBe(true);
    expect(hasBudget(15000)).toBe(true);
    expect(hasBudget(NaN)).toBe(false);
  });
  it("reports when the sentinel could have truncated the uncapped plan", () => {
    const plan = { total_upfront_usd: { low: 0, expected: 0, high: 1000 } } as never;
    expect(sentinelBinds(plan)).toBe(false);
    const huge = { total_upfront_usd: { low: 0, expected: 0, high: UNCAPPED_BUDGET_USD } } as never;
    expect(sentinelBinds(huge)).toBe(true);
  });
  it("never shows the sentinel as a dollar figure in the activity log", () => {
    const message = "3 measures within $100,000,000; 2 more financeable";
    expect(displayEventMessage(message, false)).toBe("3 measures with no budget limit; 2 more financeable");
    expect(displayEventMessage(message, true)).toBe(message);
    expect(displayEventMessage("Fetching data", false)).toBe("Fetching data");
    expect(displayEventMessage("3 measures within $15,000", false)).toBe("3 measures within $15,000");
  });
  it("suppresses the stale-summary note on the first budget entry only", () => {
    const warnings = ["re-run: the summary text was written for the earlier plan", "weather data is modelled"];
    expect(visibleWarnings(warnings, true)).toEqual(["weather data is modelled"]);
    expect(visibleWarnings(warnings, false)).toEqual(warnings);
  });
});
