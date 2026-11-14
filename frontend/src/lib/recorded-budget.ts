// Live-recording requests confirmed by the API owner on Message Board #1.
// Example-mode budgets come from the example itself, in App.choose.
const recordedBudgets: Record<string, number> = {
  zvKHR9DHNjJ: 10000,
  ZSPaQbkGcJJ: 150000,
  L3266YcPPvd: 50000,
};

export function initialConnectedBudget(sid: string): number {
  return recordedBudgets[sid] ?? 15000;
}
