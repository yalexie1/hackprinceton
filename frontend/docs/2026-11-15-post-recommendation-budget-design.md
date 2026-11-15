# Budget after recommendations — design

Date: 2026-11-15
Lane: frontend (`frontend/`, owner of record @vinayak-sinha; @vigjay is taking this work)
Status: approach and open questions settled, not yet implemented

## Intent and why

Judges told us they would rather see **what their building can actually use** before
seeing **what they can afford**. Today the product asks for a cash budget during setup,
before any analysis exists, so the first thing a person sees is already pruned by a number
they guessed. That anchors them low and hides good options.

The new order:

1. Setup asks for role, audit method and optional bills. No budget.
2. The audit runs uncapped and the results screen shows every upgrade that **applies to
   this building** — ranked by value, with no affordability language anywhere.
3. A budget prompt sits on the results screen. Entering a number re-plans and splits the
   list into the best combination that fits, options that need more budget, and the rest.

## Goals

- The pre-budget list contains only measures that genuinely apply: applicable, allowed for
  the person's role, saves energy, and cost-effective (SIR >= 1).
- After a budget is entered, the kept set is the **best combination** within it, not a
  cost-sorted truncation.
- Contractor documents are only reachable once a budget exists.
- No budget or affordability wording appears before the person has given a budget.
- Changing the budget later keeps working exactly as it does today.

## Non-goals

- No change to how measures are evaluated, costed or ranked.
- No change to `backend/schema.py` or anything under `specs/` (see Approaches).
- No new "best combination" logic in the frontend.

## Anti-goals (failure even if it ships)

- A pre-budget list padded with measures that do not apply to the building. The judges asked
  for the opposite, and it would read as noise.
- A frontend-computed split whose totals disagree with the backend's plan.
- The sentinel budget becoming visible to a user as a dollar figure.

## Constraints

- `RunRequest.budget_usd` is `float = Field(ge=0)` — required. `backend/schema.py` is generated
  from the code block in `specs/SPEC.md` section 9 and is shared contract owned by @yalexie1.
- `frontend/` is @vinayak-sinha's lane of record. @vigjay is taking the work directly, so no
  handoff is pending; AGENTS.md rule 7 still wants a board post when the change lands, because
  the setup request shape other lanes read changes with it.
- `replan()` (`backend/agent/runtime/replan.py:80`) deliberately does not regenerate the
  narrative; it appends a `re-run:` warning when the old summary's numbers no longer match.

## What the backend already gives us

`select_plan()` (`backend/analysis/finance/plan/plan.py:173`) is already the "best combination
within budget" the judges asked for:

- Measures are grouped into ordered steps, operations before solar.
- Within a step it repeatedly takes the best profitability index (NPV / net upfront) that fits
  the remaining budget, then **re-evaluates every remaining measure against the new state**, so
  interactions are honored rather than summed.
- Solar goes last, sized against the load that is left, best NPV of 100/75/50 percent; if the
  full array does not fit the leftover budget it is shrunk to that budget and kept only if it
  stays above `min_pv_kw`.
- Everything left over that is still cost-effective becomes `financeable`; everything else lands
  in `skipped` with a reason (`role`, `no_savings`, `not_cost_effective`, `no_cost_data`,
  not-applicable codes).

Run that function with a budget large enough to bind nothing and `selected` *is* the
applicable-and-cost-effective set, while `skipped` *is* the "does not apply to your building"
set. Both halves of the judges' ask fall out of existing logic.

## Approaches

**1. Uncapped first run, server replan on budget entry — chosen.**
Start the run with a documented sentinel budget. Gate every budget-dependent piece of UI behind
a "no budget yet" flag. On submit, call the existing `PATCH /runs/:id` → `replan()`, which
rebuilds model, baseline and plan from the cached bundle with no vision pass, no LLM call and no
data refetch. The existing three-way tabs in `Plan.tsx` then render the fitted plan unchanged.
No backend or contract change. Cost: `plan.budget_usd` and `request.budget_usd` hold a fake
number until the person answers, so every place that prints them needs gating.

**2. Make `budget_usd` optional in the contract.** `float | None`, None meaning no cap. Honest
semantics, no sentinel, nothing to gate. Rejected for now: it needs an edit to the `specs/SPEC.md`
section 9 block, `plan.py` handling None, a `CONTRACT-CHANGE:` post and @yalexie1's sign-off —
three lanes during a hackathon. Worth doing after the demo.

**3. Split client-side.** One uncapped run, browser does the filtering. Rejected: it cannot
reproduce solar shrink-to-remaining-budget, step ordering or interaction re-evaluation, so the
"best combination" would be wrong and the displayed totals would contradict the backend.

## The design

### Sentinel

One exported constant in the frontend, `UNCAPPED_BUDGET_USD`, with a comment explaining it stands
for "no cap" and only ever travels to the API. Value `100_000_000`: far above any plausible
retrofit (`api.test.ts` already exercises `10_000_000`) while staying an ordinary float for the
finance math.

### App state

Add `budgetEntered: boolean`, false until the person submits a budget. Derived rule used
everywhere: **show budget language only when `budgetEntered`**.

- `start()` sends `budget_usd: UNCAPPED_BUDGET_USD` and drops the budget validation.
- The setup form loses its budget field and its copy stops promising a budget question.
- Restoring a run from a URL sets `budgetEntered` from whether the saved request's budget is the
  sentinel, so a shared link resumes in the right phase.

### Results screen, before a budget

- Page subtitle drops the `· $X cash budget` clause (`App.tsx:756`).
- `Plan.tsx` metrics: "Cost to get started" loses its `of $X cash budget` line
  (`Plan.tsx:515`) and reads as the total for every applicable upgrade.
- The over-budget caution banner (`Plan.tsx:526`) is suppressed.
- Tabs collapse to two: the applicable upgrades, and "Other findings". The
  "In your plan" / "Needs more budget" distinction is meaningless with no budget, and
  `financeable` is empty anyway.
- Heading and description say these are the upgrades that suit this building, with no mention of
  affordability.

### The budget prompt

A card on the results screen, visually the next step rather than a sidebar afterthought while
`budgetEntered` is false. It takes a dollar amount and submits to the existing `update()` path.
Once a budget exists it becomes the current sidebar budget card, unchanged.

### Results screen, after a budget

Exactly today's behaviour: three tabs, totals against the budget, caution banner when the high
estimate exceeds it, and the same replan on every later change.

### Documents require a budget

`Documents.tsx:76` defaults its drafting scope to `plan.selected`, so in the pre-budget phase a
contractor packet would cover every applicable upgrade — a scope nobody has priced against their
cash. While `budgetEntered` is false the "Prepare documents" next step (`Plan.tsx`, and the
documents entry in the workspace navigation) is disabled and points at the budget prompt instead,
with a line saying a budget is needed first. Once a budget exists it behaves as it does today.

### The stale-narrative warning

`replan()` appends a `re-run:` warning whenever the narrative's numbers no longer match, and
`Warnings.tsx:10` surfaces it as "Check that the plan matches your budget". On the **first**
budget entry that is misleading — nothing is stale, this is the intended flow. Suppress `re-run:`
warnings for that first transition only; later budget changes keep the warning.

### The sentinel in the activity log

`event.message` is rendered raw at `App.tsx:877`, and `analysis_run.py:101` emits
`"N measures within $X; M more financeable"`. While `budgetEntered` is false that would print the
sentinel. A small helper rewrites the `within $<sentinel>` clause to "with no budget limit" for
display only; it leaves every other message untouched and is covered by its own test.

## What is left to the builder

- Exact copy for the pre-budget heading, description, budget prompt and the disabled-documents
  line, in the voice of the surrounding screens.
- Where precisely the budget card sits before a budget exists, and its styling.
- Whether the pre-budget tab strip keeps the tab affordance or renders as a plain list with the
  "Other findings" section below it.
- Updating `screens.test.tsx`, `fixtures.test.ts` and `recorded-budget.test.ts` for the two
  phases, plus new tests for the sentinel rewrite and the suppressed first-transition warning.
