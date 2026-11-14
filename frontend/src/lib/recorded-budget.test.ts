import { describe, expect, it } from "vitest";
import {
  initialConnectedBudget,
  initialConnectedRole,
} from "./recorded-budget";

describe("connected property audit defaults", () => {
  it("matches each saved live recording so selection does not request a different plan", () => {
    expect(initialConnectedBudget("zvKHR9DHNjJ")).toBe(10000);
    expect(initialConnectedBudget("ZSPaQbkGcJJ")).toBe(150000);
    expect(initialConnectedBudget("L3266YcPPvd")).toBe(50000);
    expect(initialConnectedBudget("new-property")).toBe(15000);
    expect(initialConnectedRole("zvKHR9DHNjJ")).toBe("owner_occupier");
    expect(initialConnectedRole("ZSPaQbkGcJJ")).toBe("landlord");
    expect(initialConnectedRole("L3266YcPPvd")).toBe("landlord");
    expect(initialConnectedRole("new-property")).toBe("owner_occupier");
  });
});
