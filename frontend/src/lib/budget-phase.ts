import { money } from "./format";
import type { Plan } from "./types";

// `RunRequest.budget_usd` is a required contract field, so the first (uncapped) audit run
// sends this sentinel in its place to signal "no budget limit" without binding anything.
export const UNCAPPED_BUDGET_USD = 100_000_000;

export function hasBudget(budgetUsd: number): boolean {
  return Number.isFinite(budgetUsd) && budgetUsd !== UNCAPPED_BUDGET_USD;
}

export function sentinelBinds(plan: Plan): boolean {
  return plan.total_upfront_usd.high >= UNCAPPED_BUDGET_USD;
}

const SENTINEL_WITHIN = `within ${money(UNCAPPED_BUDGET_USD)}`;

export function displayEventMessage(message: string, budgeted: boolean): string {
  if (budgeted) return message;
  return message.replace(SENTINEL_WITHIN, "with no budget limit");
}

export function visibleWarnings(warnings: string[], suppressReplanNotes: boolean): string[] {
  if (!suppressReplanNotes) return warnings;
  return warnings.filter((w) => !w.startsWith("re-run:"));
}
