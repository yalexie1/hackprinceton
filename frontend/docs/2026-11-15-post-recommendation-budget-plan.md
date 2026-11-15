# Budget After Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move budget entry out of audit setup and onto the results screen, so a person first sees every upgrade that applies to their building and only then sees which combination their cash buys.

**Architecture:** The run starts with a sentinel budget that binds nothing, so the backend's existing `select_plan` returns the whole applicable-and-cost-effective set in `plan.selected`. The phase is derived from `run.request.budget_usd` rather than stored in React state, so a restored link resumes in the right phase with no extra plumbing. Entering a budget goes through the existing `PATCH /runs/:id` → `replan()` path, after which every screen behaves exactly as it does today.

**Tech Stack:** React 19, TypeScript, Vite, vitest. Component tests render with `renderToStaticMarkup` and assert on the HTML string — there is no jsdom or testing-library in this project, so all branching logic that needs direct testing lives in `src/lib/` as pure functions.

**Spec:** `frontend/docs/2026-11-15-post-recommendation-budget-design.md`

## Anchors are content, not line numbers

`App.tsx` and `Plan.tsx` both changed while this plan was being written — a `homeowner-language`
translation layer landed, and App gained an export feature. Every reference below names the code
to find rather than trusting a line number, and the numbers quoted are from `main` at
`budget-after-recommendations`. Re-grep before editing.

Two integration points that layer creates:

- The activity log renders `auditEventText(event)` (`App.tsx:880`), inside a `collapseActivity`
  wrapper keyed on the same text. `auditEventText` falls through to `readableText`, which was
  verified to leave `"3 measures within $100,000,000; 2 more financeable"` byte-for-byte
  unchanged — so the sentinel really does reach the screen, and `displayEventMessage` must wrap
  the *output* of `auditEventText`, not replace it.
- Warnings reach `Warnings` from two call sites, `App.tsx:1015` and `App.tsx:1178`, and are
  translated by `warningText`. `visibleWarnings` filters the raw strings before either call, so
  it must match on the raw `re-run:` prefix, not on translated copy.

## Deviation from the design

The design proposed a `budgetEntered: boolean` in App state. This plan derives the phase from
`run.request.budget_usd` instead. It is the same information with one source of truth, it makes a
restored link resume in the right phase with no extra code, and it means `PlanView`'s props do not
change — so the five existing `PlanView` renders in `screens.test.tsx` keep working untouched.

## Global Constraints

- `UNCAPPED_BUDGET_USD = 100_000_000`. Defined once, in `src/lib/budget-phase.ts`, and never rendered to a person.
- The phase is always `hasBudget(run.request.budget_usd)`. Never a separate state flag, never read from `plan.budget_usd` (the plan is absent while a run is in flight).
- No file outside `frontend/` is touched. No change to `backend/schema.py` or `specs/`.
- Before a budget exists, no screen may contain the words "budget", "afford", "cash" or a dollar cap. Tests assert the absence.
- Run from `frontend/`: `npm test` for the suite, `npx vitest run <path>` for one file.

## Review Focus

1. **A restored link to an uncapped run** must resume in the pre-budget phase — Task 1's `hasBudget` test covers the sentinel round-trip.
2. **A budget of exactly 0** is valid per `Field(ge=0)` and makes `selected` empty and everything `financeable`. The empty state must say the budget is too small, not that nothing applies to the building — Task 2.
3. **A budget field typed then cleared** leaves `NaN`; submitting must be refused rather than sending `NaN` to the API — Task 3.
4. **An uncapped run where every measure is skipped** (nothing applies at all) must give an empty state with no budget language — Task 2.
5. **A plan whose total high upfront exceeds the sentinel** would be silently truncated. `hasBudget` cannot catch it, so Task 1 exposes `sentinelBinds(plan)` and Task 2 renders a plain note if it is ever true — Task 1 and Task 2.

---

## File Structure

- Create: `frontend/src/lib/budget-phase.ts` — the sentinel, the phase predicate, the two display filters. Pure, no React.
- Create: `frontend/src/lib/budget-phase.test.ts`
- Create: `frontend/src/components/BudgetPrompt.tsx` — the budget form, in both its pre-budget (prominent) and post-budget (sidebar) presentations.
- Create: `frontend/src/components/BudgetPrompt.test.tsx`
- Modify: `frontend/src/components/Plan.tsx` — derive the phase; gate budget copy, the over-budget banner, the third tab and the documents step.
- Modify: `frontend/src/components/WorkspaceNavigation.tsx` — accept disabled views.
- Modify: `frontend/src/App.tsx` — drop the setup budget field, send the sentinel, place `BudgetPrompt`, filter activity messages and warnings, pass disabled views.
- Modify: `frontend/src/components/screens.test.tsx`, `frontend/src/components/WorkspaceNavigation.test.tsx`

---

### Task 1: Budget phase helpers

**Files:**
- Create: `frontend/src/lib/budget-phase.ts`
- Test: `frontend/src/lib/budget-phase.test.ts`

**Interfaces:**
- Consumes: `Plan` from `./types`.
- Produces:
  - `export const UNCAPPED_BUDGET_USD = 100_000_000`
  - `export function hasBudget(budgetUsd: number): boolean`
  - `export function sentinelBinds(plan: Plan): boolean`
  - `export function displayEventMessage(message: string, budgeted: boolean): string`
  - `export function visibleWarnings(warnings: string[], suppressReplanNotes: boolean): string[]`

- [ ] **Step 1: Write the failing tests**

```ts
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/lib/budget-phase.test.ts`
Expected: FAIL — cannot resolve `./budget-phase`.

- [ ] **Step 3: Implement the five exports in `frontend/src/lib/budget-phase.ts`**

`hasBudget` is `Number.isFinite(budgetUsd) && budgetUsd !== UNCAPPED_BUDGET_USD`. `sentinelBinds` is `plan.total_upfront_usd.high >= UNCAPPED_BUDGET_USD`. `displayEventMessage` replaces only the sentinel's own `money()`-formatted form — build the needle from `UNCAPPED_BUDGET_USD` so the constant stays the single source of truth, and rewrite `within <needle>` to `with no budget limit`. `visibleWarnings` drops entries starting with `re-run:` when `suppressReplanNotes`. File header comment: one sentence on why a sentinel exists and that `budget_usd` is a required contract field.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/lib/budget-phase.test.ts`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/budget-phase.ts frontend/src/lib/budget-phase.test.ts
git commit -m "frontend: add budget phase helpers for the uncapped first run"
```

---

### Task 2: Pre-budget plan screen

**Files:**
- Modify: `frontend/src/components/Plan.tsx` (`PlanView`, from line 452)
- Test: `frontend/src/components/screens.test.tsx`

**Interfaces:**
- Consumes: Task 1's `UNCAPPED_BUDGET_USD`, `hasBudget`, `sentinelBinds`.
- Produces: no new exports. `PlanView`'s props are unchanged — the phase is derived inside from `run.request.budget_usd`, so the five existing `PlanView` renders in `screens.test.tsx` keep working untouched.

- [ ] **Step 1: Write the failing tests**

Append to the `shared contract screen compatibility` describe block in `screens.test.tsx`. `uncapped(run)` is a local helper that clones a run and sets both `request.budget_usd` and `plan.budget_usd` to `UNCAPPED_BUDGET_USD`.

```tsx
it("shows what applies to the building with no budget language before a budget is given", () => {
  const html = renderToStaticMarkup(
    <PlanView run={uncapped(house)} onFocus={() => {}} onDocuments={() => {}} />,
  );
  expect(html).not.toContain("100,000,000");
  expect(html).not.toMatch(/budget/i);
  expect(html).not.toContain("Needs more budget");
  expect(html).toContain("Other findings");
  expect(html).toContain("apply to your building");
});
it("restores the three budget tabs once a budget exists", () => {
  const html = renderToStaticMarkup(
    <PlanView run={house} onFocus={() => {}} onDocuments={() => {}} />,
  );
  expect(html).toContain("Needs more budget");
  expect(html).toContain("cash budget");
});
it("blames a too-small budget rather than the building when nothing is selected", () => {
  const run = structuredClone(house);
  run.request.budget_usd = 0;
  run.plan!.budget_usd = 0;
  run.plan!.selected = [];
  const html = renderToStaticMarkup(<PlanView run={run} onFocus={() => {}} onDocuments={() => {}} />);
  expect(html).toMatch(/budget/i);
  expect(html).not.toContain("apply to your building");
});
it("gives an empty state with no budget language when nothing applies to the building", () => {
  const run = uncapped(house);
  run.plan!.selected = [];
  run.plan!.financeable = [];
  const html = renderToStaticMarkup(<PlanView run={run} onFocus={() => {}} onDocuments={() => {}} />);
  expect(html).not.toMatch(/budget/i);
});
it("says so if the uncapped run could have been truncated by the sentinel", () => {
  const run = uncapped(house);
  run.plan!.total_upfront_usd.high = UNCAPPED_BUDGET_USD;
  const html = renderToStaticMarkup(<PlanView run={run} onFocus={() => {}} onDocuments={() => {}} />);
  expect(html).toContain("may not be complete");
});
it("sends a person to the budget before offering contractor documents", () => {
  const html = renderToStaticMarkup(
    <PlanView run={uncapped(house)} onFocus={() => {}} onDocuments={() => {}} />,
  );
  expect(html).toContain("disabled");
  expect(html).not.toContain("Prepare documents");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/components/screens.test.tsx`
Expected: FAIL — the pre-budget assertions fail; the existing tests in the file still pass.

- [ ] **Step 3: Derive the phase in `PlanView` and gate on it**

`const budgeted = hasBudget(run.request.budget_usd)`. When false:
- "Cost to get started" drops its `of {money(plan.budget_usd)} cash budget` line (`Plan.tsx:516`).
- The over-budget banner (`className="inline-note budget-warning"`, `Plan.tsx:527`) does not render.
- The tab strip offers `selected` and `skipped` only. The `selected` tab is labelled for applicability, not inclusion; its heading and description say these are the upgrades that apply to this building and that a budget comes next. None of this copy uses the words in the Global Constraints list.
- The `next-step` block (`Plan.tsx:705`) renders with its button `disabled` and a line saying a budget is needed before documents can be drafted.
- If `sentinelBinds(plan)`, a `fineprint` note says the list may not be complete.

When true, every one of those renders exactly as it does today. The empty-state copy at `Plan.tsx:667` branches on `budgeted`: with a budget it talks about the budget being too small, without one it says nothing applies.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/components/screens.test.tsx`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Plan.tsx frontend/src/components/screens.test.tsx
git commit -m "frontend: show the applicable upgrade set before a budget is given"
```

---

### Task 3: Budget prompt component

**Files:**
- Create: `frontend/src/components/BudgetPrompt.tsx`
- Test: `frontend/src/components/BudgetPrompt.test.tsx`

**Interfaces:**
- Consumes: Task 1's `hasBudget`; `money` from `../lib/format`.
- Produces: `export default function BudgetPrompt(props: { budget: number; budgeted: boolean; busy: boolean; replay: boolean; onBudgetChange: (value: number) => void; onSubmit: () => void }): JSX.Element`

- [ ] **Step 1: Write the failing tests**

```tsx
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import BudgetPrompt from "./BudgetPrompt";

const props = { budget: 15000, busy: false, replay: false, onBudgetChange: () => {}, onSubmit: () => {} };

describe("budget prompt", () => {
  it("asks for a budget as the next step before one exists", () => {
    const html = renderToStaticMarkup(<BudgetPrompt {...props} budgeted={false} />);
    expect(html).toContain("budget-prompt");
    expect(html).toContain("fit");
  });
  it("becomes the sidebar budget control once a budget exists", () => {
    const html = renderToStaticMarkup(<BudgetPrompt {...props} budgeted />);
    expect(html).toContain("budget-card");
    expect(html).toContain("Update plan");
  });
  it("refuses to submit a cleared field", () => {
    const html = renderToStaticMarkup(<BudgetPrompt {...props} budget={NaN} budgeted={false} />);
    expect(html).toContain("disabled");
  });
  it("says a replayed plan is only re-checked", () => {
    const html = renderToStaticMarkup(<BudgetPrompt {...props} budgeted replay />);
    expect(html).toContain("Update budget");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/components/BudgetPrompt.test.tsx`
Expected: FAIL — cannot resolve `./BudgetPrompt`.

- [ ] **Step 3: Implement `BudgetPrompt`**

Move the form currently inline at `App.tsx:1065-1136` into this component, keeping its markup, its `currency-input` styling and its existing copy for the budgeted case. The submit button is `disabled` when `busy` or `Number.isNaN(budget)`. The unbudgeted case renders with class `budget-prompt` instead of `budget-card`, a heading that asks what the person can spend upfront, and a line saying the plan will be rebuilt to the best combination that fits. The "Operations first. Solar last." rule line stays in the budgeted case only.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/components/BudgetPrompt.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/BudgetPrompt.tsx frontend/src/components/BudgetPrompt.test.tsx
git commit -m "frontend: extract the budget form into BudgetPrompt with a pre-budget presentation"
```

---

### Task 4: Disabled navigation entries

**Files:**
- Modify: `frontend/src/components/WorkspaceNavigation.tsx`
- Test: `frontend/src/components/WorkspaceNavigation.test.tsx`

**Interfaces:**
- Produces: `WorkspaceNavigation` gains two optional props — `disabledViews?: ReadonlySet<View>` and `disabledHint?: string`. Omitting them leaves today's behaviour.

- [ ] **Step 1: Write the failing test**

```tsx
it("disables a view that is not reachable yet and says why", () => {
  const html = renderToStaticMarkup(
    <WorkspaceNavigation
      view="plan" complete hasRun busy={false} needsInput={false} propertyName="Test"
      onNavigate={() => {}}
      disabledViews={new Set<View>(["documents"])}
      disabledHint="Enter a budget first"
    />,
  );
  expect(html).toMatch(/Documents[\s\S]{0,200}?disabled|disabled[\s\S]{0,200}?Documents/);
  expect(html).toContain("Enter a budget first");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run src/components/WorkspaceNavigation.test.tsx`
Expected: FAIL — the props do not exist.

- [ ] **Step 3: Honour `disabledViews` in `link()`**

A disabled entry renders `disabled` and carries `disabledHint` as its `title`, and `onNavigate` is not wired to it.

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/components/WorkspaceNavigation.test.tsx`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WorkspaceNavigation.tsx frontend/src/components/WorkspaceNavigation.test.tsx
git commit -m "frontend: let workspace navigation disable a view that is not reachable yet"
```

---

### Task 5: Wire the flow in App

**Files:**
- Modify: `frontend/src/App.tsx`
- Test: the whole suite, plus `npm run build` for the type check.

**Interfaces:**
- Consumes: every export from Tasks 1, 3 and 4.
- Produces: nothing new.

- [ ] **Step 1: Remove the budget question from setup**

Delete the `Upfront cash budget` label and both its branches (`App.tsx:597-636`) — this removes the dead `demo` select and the now-unused `budgets` array at `App.tsx:135`. The setup description at `App.tsx:564` stops promising a budget question and says the audit finds what suits the building. `start()` sends `budget_usd: UNCAPPED_BUDGET_USD` and drops the budget validation at `App.tsx:341`.

- [ ] **Step 2: Derive the phase and place the prompt**

`const budgeted = run ? hasBudget(run.request.budget_usd) : false`. Render `<BudgetPrompt>` with `budgeted={false}` directly above `<PlanView>` in the plan view's main column when the run is `done` and not budgeted; keep it in the `result-aside` with `budgeted` when it is. The page subtitle at `App.tsx:759` drops its `· {money(...)} cash budget` clause when not budgeted.

- [ ] **Step 3: Suppress the first-entry stale note and the sentinel in the log**

Add a `firstBudgetEntry = useRef(false)` set true in the `BudgetPrompt` submit handler when `!budgeted`, and cleared whenever `update()` is called while already budgeted. Pass `visibleWarnings(run.warnings, firstBudgetEntry.current)` at both `Warnings` call sites
(`App.tsx:1015` and the spread at `App.tsx:1178`). Wrap the activity-log text as
`displayEventMessage(auditEventText(event), budgeted)` at `App.tsx:880`. Note in a comment that a page reload after the first entry will show the note again, which is accurate rather than wrong: the saved narrative really was written for the uncapped plan.

- [ ] **Step 4: Gate documents**

Pass `disabledViews={budgeted ? undefined : new Set(["documents"])}` and a `disabledHint` to `WorkspaceNavigation`, and make `setView("documents")` a no-op while not budgeted so a stale deep link cannot reach it.

- [ ] **Step 5: Run the whole suite and the build**

Run: `npm test && npm run build`
Expected: all tests pass; `tsc -b` reports no errors. Fix any call site the removed `budgets` array left behind.

- [ ] **Step 6: Verify the real flow in the browser**

Start the dev server, run an audit, and confirm: setup has no budget field; the results screen lists the applicable upgrades with no budget wording and a disabled Documents entry; entering a budget re-plans and the three tabs appear with totals against it; no screen or activity line ever shows `100,000,000`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "frontend: ask for the budget after the recommendations, not before"
```

---

## After the plan

Post on the board (AGENTS.md rule 7) when this lands: the setup request shape changed, every live run now starts uncapped and is re-planned on budget entry, and other lanes reading `RunRequest.budget_usd` should know a sentinel can appear there.
