import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronRight,
  Coins,
  Info,
  Leaf,
  Lightbulb,
  Sun,
  Thermometer,
  Wind,
} from "lucide-react";
import { useId, useState } from "react";
import type {
  Assumption,
  FinancingScenario,
  MeasureResult,
  Ranged,
  RunResult,
} from "../lib/types";
import { readableText, warningText } from "../lib/homeowner-language";
import { hasBudget, sentinelBinds } from "../lib/budget-phase";
import { SourceDrawer } from "./SourceDrawer";
import { REASON_DETAIL, REASON_LABELS, measureName } from "./FindingReason";
import { money, number, ranged } from "../lib/format";
const reasonLabels = REASON_LABELS;
export function FinancingTerms({
  scenario: s,
}: {
  scenario: FinancingScenario;
}) {
  const complete = s.rate != null && s.term_years != null && s.term_years > 0;
  return complete ? (
    <>
      <p>
        {money(s.financed_usd)} financed · {number(s.rate! * 100, 2)}% interest
        · {s.term_years} years · {money(s.annual_payment_usd)} yearly financing
        payment
      </p>
      <p>
        First-year savings after financing payments:{" "}
        {money(s.net_cashflow_year1_usd.expected)} (
        {ranged(s.net_cashflow_year1_usd, true)})
      </p>
    </>
  ) : (
    <p>
      Loan terms still need confirmation. Payment and savings after loan
      payments will be shown once an interest rate and repayment period are
      available.
    </p>
  );
}
export function Range({
  value,
  currency = false,
  suffix = "",
}: {
  value: Ranged;
  currency?: boolean;
  suffix?: string;
}) {
  return (
    <span className="range-value">
      <strong>
        {currency ? money(value.expected) : number(value.expected, 2)}
        {suffix}
      </strong>
      {value.low !== value.high && (
        <small>
          Estimated range: {ranged(value, currency)}
          {suffix}
        </small>
      )}
    </span>
  );
}
export function MeasureIcon({ id }: { id: string }) {
  const Icon =
    id === "PV_ROOF"
      ? Sun
      : id.startsWith("HVAC")
        ? Thermometer
        : id === "ENV_AIRSEAL"
          ? Wind
          : id === "LAYOUT"
            ? Leaf
            : Lightbulb;
  return <Icon size={20} />;
}
/**
 * One "other finding", with the reason it was left out and - on opening - what that reason means
 * and what would change it. The backend's one-liner is the summary; the explanation never
 * introduces a number the backend did not give.
 */
function SkippedItem({
  item,
  title,
}: {
  item: { measure_id: string; reason: string; detail: string };
  title: string;
}) {
  const [open, setOpen] = useState(false);
  const explain = REASON_DETAIL[item.reason];
  return (
    <div
      className={`skipped-item reason-${item.reason} ${open ? "expanded" : ""}`}
    >
      <button
        className="skipped-summary"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span>
          <ChevronDown size={16} className={open ? "rotate" : ""} />
          {title}
        </span>
        <strong>
          {reasonLabels[item.reason] || item.reason.replaceAll("_", " ")}
        </strong>
      </button>
      <p className="skipped-detail">
        {/\b(SIR|NPV|IRR)\b/.test(item.detail) && explain
          ? explain.what.split(". ")[0] + "."
          : readableText(item.detail)}
      </p>
      {open && explain && (
        <div className="skipped-explain">
          <h4>What this means</h4>
          <p>{explain.what}</p>
          <h4>What would change it</h4>
          <p>{explain.change}</p>
          <details>
            <summary>Read the audit’s explanation</summary>
            <p>{readableText(item.detail)}</p>
          </details>
        </div>
      )}
      {open && !explain && (
        <p className="fineprint">
          No further explanation is recorded for this reason.
        </p>
      )}
    </div>
  );
}

export function MeasureCard({
  measure,
  rank,
  onFocus,
  assumptions = [],
  defaultOpen = false,
}: {
  measure: MeasureResult;
  rank?: number;
  onFocus: (id: string) => void;
  assumptions?: Assumption[];
  // Lets a static-markup test render the expanded detail grid directly, without a click
  // handler to drive. Production callers never pass this; it always starts collapsed.
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [sources, setSources] = useState(false);
  const f = measure.finance;
  return (
    <article className={`measure-card ${open ? "expanded" : ""}`}>
      <button
        className="measure-summary"
        onClick={() => {
          setOpen(!open);
          onFocus(measure.measure_id);
        }}
        aria-expanded={open}
      >
        <span
          className={`measure-symbol ${measure.measure_id === "PV_ROOF" ? "solar" : ""}`}
        >
          <MeasureIcon id={measure.measure_id} />
        </span>
        <span className="measure-title">
          <span>
            {rank != null && (
              <small className="rank">{String(rank).padStart(2, "0")}</small>
            )}
            {measure.title}
          </span>
          <small>
            {f?.net_upfront_usd.expected === 0
              ? "No upfront cost"
              : f
                ? `${money(f.net_upfront_usd.expected)} expected upfront`
                : "Cost unavailable"}
          </small>
        </span>
        <span className="measure-saving">
          {f && (
            <>
              <strong>
                {money(f.annual_savings_usd.expected)}
                <small>/yr</small>
              </strong>
              <small>{ranged(f.annual_savings_usd, true)}</small>
            </>
          )}
        </span>
        <ChevronDown size={16} className={open ? "rotate" : ""} />
      </button>
      {open && (
        <div className="measure-details">
          <p>{readableText(measure.description)}</p>
          {/* One click to the provenance, and nothing added to the page until asked:
              a source for every estimate, with the main pages kept clean. */}
          <button className="source-link" onClick={() => setSources(true)}>
            <Info size={14} /> How this was calculated
          </button>
          {sources && (
            <SourceDrawer
              measure={measure}
              assumptions={assumptions}
              onClose={() => setSources(false)}
            />
          )}
          {f && (
            <>
              <div className="detail-grid">
                <div>
                  <span>Installed cost</span>
                  <Range value={f.installed_cost_usd} currency />
                </div>
                <div>
                  <span>Cash needed upfront</span>
                  <Range value={f.net_upfront_usd} currency />
                </div>
                <div>
                  <span>Time to earn back the cost</span>
                  {f.simple_payback_years ? (
                    <Range value={f.simple_payback_years} suffix=" yrs" />
                  ) : (
                    <strong>
                      {f.net_upfront_usd.expected === 0
                        ? "No upfront cost"
                        : "Not available"}
                    </strong>
                  )}
                </div>
                <div>
                  <span>Estimated benefit over the upgrade’s life</span>
                  <Range value={f.npv_usd} currency />
                  <small>Savings minus costs, in today’s dollars.</small>
                </div>
              </div>
              <details className="financial-guide">
                <summary>Detailed return calculations</summary>
                <div className="detail-grid">
                  <div>
                    <span>Discounted payback</span>
                    <strong>
                      {f.discounted_payback_years == null
                        ? "Not available"
                        : `${number(f.discounted_payback_years, 1)} years`}
                    </strong>
                  </div>
                  <div>
                    <span>Useful life</span>
                    <strong>{f.useful_life_years} years</strong>
                  </div>
                  <div>
                    <span>Savings compared with cost (SIR)</span>
                    <strong>
                      {f.sir == null ? "Not available" : number(f.sir, 2)}
                    </strong>
                  </div>
                  <div>
                    <span>Internal rate of return (IRR)</span>
                    <strong>
                      {f.irr == null
                        ? "Not available"
                        : `${number(f.irr * 100, 1)}%`}
                    </strong>
                  </div>
                  <div>
                    <span>Yearly maintenance cost change</span>
                    <strong>{money(f.annual_om_change_usd)}</strong>
                  </div>
                </div>
              </details>
              <details className="financial-guide">
                <summary>What do these financial terms mean?</summary>
                <dl>
                  <dt>Simple payback</dt>
                  <dd>
                    How long estimated yearly savings take to recover the
                    upfront cost.
                  </dd>
                  <dt>Discounted payback</dt>
                  <dd>
                    Payback after allowing for the lower value of money received
                    in the future.
                  </dd>
                  <dt>Net present value (NPV)</dt>
                  <dd>
                    Future savings minus costs, expressed in today’s dollars.
                    Positive values indicate a financial benefit under the
                    stated assumptions.
                  </dd>
                  <dt>Savings-to-investment ratio (SIR)</dt>
                  <dd>
                    Discounted lifetime savings compared with the investment. A
                    ratio of at least 1 passes the plan’s cost-effectiveness
                    test.
                  </dd>
                  <dt>Internal rate of return (IRR)</dt>
                  <dd>
                    The discount rate at which the project’s net present value
                    is zero.
                  </dd>
                  <dt>Estimated range</dt>
                  <dd>
                    The low and high estimates supplied by the analysis. These
                    are estimates, not contractor quotes or guaranteed savings.
                  </dd>
                </dl>
              </details>
              {measure.savings && (
                <div className="detail-grid">
                  <div>
                    <span>Electricity saved / year</span>
                    <Range
                      value={measure.savings.electricity_kwh}
                      suffix=" kWh"
                    />
                  </div>
                  <div>
                    <span>Gas saved / year</span>
                    <Range
                      value={measure.savings.gas_kwh}
                      suffix=" kWh thermal"
                    />
                  </div>
                  <div>
                    <span>CO₂ avoided / year</span>
                    <Range value={measure.savings.co2_kg} suffix=" kg" />
                  </div>
                </div>
              )}
              <p className="fineprint">
                {f.analysis_period_years}-year analysis ·{" "}
                {number(f.discount_rate * 100, 1)}% discount rate · electricity
                price increase {number(f.electricity_escalation * 100, 1)}% per
                year · gas price increase {number(f.gas_escalation * 100, 1)}%
                per year. Cost source: {f.cost_source}.
              </p>
              <div className="incentives">
                <strong>Incentives</strong>
                {f.incentives.length ? (
                  f.incentives.map((i, index) => (
                    <p key={index}>
                      {i.name} · {i.status} · {ranged(i.amount_usd, true)}
                      <small>
                        {i.kind.replaceAll("_", " ")}
                        {i.eligibility
                          ? ` · Project eligibility: ${i.eligibility.replaceAll("_", " ")}`
                          : ""}
                      </small>
                      {i.conditions?.map((condition, j) => (
                        <small key={j}>{condition}</small>
                      ))}
                      <small>{i.citation}</small>
                    </p>
                  ))
                ) : (
                  <p>
                    No incentive applied. Tax benefits do not reduce the upfront
                    cost.
                  </p>
                )}
              </div>
              {f.financing
                .filter((s) => s.kind === "cpace")
                .map((s, i) => (
                  <div className="finance-box" key={i}>
                    <strong>
                      Property-tax financing (C-PACE) ·{" "}
                      {s.eligible
                        ? "Eligible per analysis"
                        : "Eligibility not established"}
                    </strong>
                    <p className="field-help">
                      Financing is repaid through a property-tax assessment.
                      Availability and eligibility must be confirmed.
                    </p>
                    <FinancingTerms scenario={s} />
                    {s.program_sir != null && (
                      <p>
                        Financing programme’s savings ratio:{" "}
                        {number(s.program_sir, 2)}
                      </p>
                    )}
                    {s.notes.map((note, j) => (
                      <small key={j}>{note}</small>
                    ))}
                  </div>
                ))}
            </>
          )}
          {measure.evidence.length > 0 && (
            <div className="evidence">
              <span>Evidence</span>
              {measure.evidence.map((e, i) => (
                <p key={i}>
                  {e.kind.replaceAll("_", " ")} · {e.ref}
                  {e.note && <small>{e.note}</small>}
                </p>
              ))}
              <button
                className="text-button"
                onClick={() => onFocus(measure.measure_id)}
              >
                Locate in building <ArrowUpRight size={14} />
              </button>
            </div>
          )}
          {measure.value_uplift && (
            <div className="value-uplift">
              <h3>Estimated solar property value uplift</h3>
              <Range value={measure.value_uplift.value_usd} currency />
              <p className="fineprint">
                Shown separately from energy savings and financial returns.
                Method {measure.value_uplift.method}.
              </p>
              {measure.value_uplift.notes.map((note, i) => (
                <p className="fineprint" key={i}>
                  {readableText(note)}
                </p>
              ))}
            </div>
          )}
          {measure.flags.map((flag) => (
            <p className="inline-note" key={flag.key}>
              <Info size={14} />
              {warningText(flag.message)}
            </p>
          ))}
          {measure.warnings.map((w, i) => (
            <p className="fineprint" key={i}>
              {warningText(w)}
            </p>
          ))}
        </div>
      )}
    </article>
  );
}
export default function PlanView({
  run,
  onFocus,
  onDocuments,
  initialTab = "selected",
}: {
  run: RunResult;
  onFocus: (id: string) => void;
  onDocuments: () => void;
  // Lets a static-markup test render a non-default tab panel directly, without a click
  // handler to drive. Production callers never pass this; it always starts on "selected".
  initialTab?: "selected" | "financeable" | "skipped";
}) {
  const plan = run.plan;
  const budgeted = hasBudget(run.request.budget_usd);
  const [tab, setTab] = useState<"selected" | "financeable" | "skipped">(
    initialTab,
  );
  const tabsId = useId();
  if (!plan)
    return (
      <div className="empty-state">
        <Leaf />
        <h3>Your plan is taking shape</h3>
        <p>The audit will publish the ranked measures here.</p>
      </div>
    );
  const skipped = [
    ...plan.skipped.filter(
      (item) =>
        !(
          item.reason === "over_budget" &&
          (plan.financeable.some(
            (measure) => measure.measure_id === item.measure_id,
          ) ||
            !budgeted)
        ),
    ),
    ...run.measures
      .filter(
        (m) =>
          !m.applicable &&
          !plan.skipped.some((s) => s.measure_id === m.measure_id),
      )
      .map((m) => ({
        measure_id: m.measure_id,
        reason: "not_applicable",
        detail:
          m.not_applicable_reason ||
          "This measure does not apply to the current building.",
      })),
  ];
  return (
    <>
      <div className="metrics">
        <div className="metric featured">
          <span>
            <ArrowDownRight size={16} />
            Save on energy bills
          </span>
          <Range value={plan.total_annual_savings_usd} currency />
          <small>estimated each year</small>
        </div>
        <div className="metric">
          <span>
            <Coins size={16} />
            Cost to get started
          </span>
          <Range value={plan.total_upfront_usd} currency />
          {budgeted && <small>of {money(plan.budget_usd)} cash budget</small>}
        </div>
        <div className="metric">
          <span>
            <Leaf size={16} />
            Emissions reduced
          </span>
          <Range value={plan.total_co2_kg} suffix=" kg" />
          <small>kilograms of carbon dioxide each year</small>
        </div>
      </div>
      {budgeted && plan.total_upfront_usd.high > plan.budget_usd && (
        <p className="inline-note budget-warning">
          <Info size={15} />
          {plan.total_upfront_usd.expected > plan.budget_usd
            ? "The returned plan exceeds your cash budget at expected costs. Request a revised plan before proceeding."
            : "The plan fits at expected costs. The upper estimate may exceed your cash budget; confirm contractor pricing before proceeding."}
        </p>
      )}
      <section className="recommendations">
        <div className="section-heading">
          <div>
            <span className="eyebrow">YOUR IMPROVEMENT OPTIONS</span>
            <h2>Choose the right next steps.</h2>
          </div>
          <span className="count-pill">{plan.selected.length} upgrades</span>
        </div>
        <p className="section-description">
          {budgeted
            ? "Start with the improvements that offer the best value for your budget. Open any recommendation to see what it costs, what it could save, and what needs checking before you hire a contractor."
            : "These are the upgrades that apply to your building. Open any recommendation to see what it costs, what it could save, and what needs checking before you hire a contractor."}
        </p>
        <div
          className="tabs plan-tabs"
          role="tablist"
          aria-label="Retrofit recommendations"
        >
          {(budgeted
            ? (["selected", "financeable", "skipped"] as const)
            : (["selected", "skipped"] as const)
          ).map((t) => (
            <button
              key={t}
              id={`${tabsId}-${t}`}
              className={`plan-tab ${t}`}
              data-category={t}
              role="tab"
              aria-selected={tab === t}
              aria-controls={`${tabsId}-panel`}
              tabIndex={tab === t ? 0 : -1}
              onClick={() => setTab(t)}
              onKeyDown={(event) => {
                const order: readonly ("selected" | "financeable" | "skipped")[] =
                  budgeted
                    ? ["selected", "financeable", "skipped"]
                    : ["selected", "skipped"];
                const index = order.indexOf(t);
                const last = order.length - 1;
                const next =
                  event.key === "ArrowRight"
                    ? order[(index + 1) % order.length]
                    : event.key === "ArrowLeft"
                      ? order[(index + last) % order.length]
                      : event.key === "Home"
                        ? order[0]
                        : event.key === "End"
                          ? order[last]
                          : null;
                if (!next) return;
                event.preventDefault();
                setTab(next);
                event.currentTarget.parentElement
                  ?.querySelector<HTMLButtonElement>(
                    `[data-category="${next}"]`,
                  )
                  ?.focus();
              }}
            >
              {t === "selected" ? (
                <Check size={20} />
              ) : t === "financeable" ? (
                <Coins size={20} />
              ) : (
                <Info size={20} />
              )}
              {t === "selected"
                ? budgeted
                  ? plan.total_upfront_usd.expected > plan.budget_usd
                    ? "Selected upgrades"
                    : "In your plan"
                  : "Applies to your building"
                : t === "financeable"
                  ? "Needs more budget"
                  : "Other findings"}
              <span>{t === "skipped" ? skipped.length : plan[t].length}</span>
            </button>
          ))}
        </div>
        <div
          className={`measure-list category-${tab}`}
          role="tabpanel"
          id={`${tabsId}-panel`}
          aria-labelledby={`${tabsId}-${tab}`}
          tabIndex={0}
        >
          <div className={`category-explanation ${tab}`}>
            <h3>
              {tab === "selected"
                ? budgeted
                  ? "Included in your current plan"
                  : "Upgrades that apply to your building"
                : tab === "financeable"
                  ? "Options beyond the current cash budget"
                  : "Why other upgrades were left out"}
            </h3>
            <p>
              {tab === "selected"
                ? budgeted
                  ? "These upgrades contribute to the savings totals above. Expand an upgrade to see its costs, estimated savings and supporting evidence."
                  : "These upgrades apply to your building and clear the cost-effectiveness test. Enter what you can spend next to see which of these fit your plan."
                : tab === "financeable"
                  ? "These upgrades pass the analysis’s cost-effectiveness test but are outside your current plan. Their savings are not included in your totals. More budget or suitable financing may make them possible."
                  : "These findings may not apply to your building, may depend on another upgrade, or may not justify their cost. Each item shows the reason from the analysis."}
            </p>
          </div>
          {tab === "selected" &&
            plan.selected.map((item) => (
              <MeasureCard
                key={item.measure.measure_id}
                measure={item.measure}
                rank={item.rank}
                onFocus={onFocus}
                assumptions={run.building_model?.assumptions ?? []}
              />
            ))}
          {tab === "financeable" && (
            <>
              <p className="fineprint">
                Financing requires separate checks. Being listed here does not
                mean a loan or C-PACE programme is available.
              </p>
              {plan.financeable.map((m) => (
                <MeasureCard
                  key={m.measure_id}
                  measure={m}
                  onFocus={onFocus}
                  assumptions={run.building_model?.assumptions ?? []}
                />
              ))}
            </>
          )}
          {tab === "skipped" &&
            skipped.map((item, i) => (
              <SkippedItem
                key={i}
                item={item}
                title={measureName(
                  item.measure_id,
                  run.measures.find((m) => m.measure_id === item.measure_id)
                    ?.title,
                )}
              />
            ))}
          {(tab === "skipped" ? skipped.length : plan[tab].length) === 0 && (
            <div className="empty-state small">
              <Check />
              <p>
                {tab === "selected"
                  ? budgeted
                    ? plan.financeable.length
                      ? "No upgrades are included in the current plan. Check Needs more budget for additional options."
                      : "No upgrades are included in the current plan. Open Other findings to see why they were left out."
                    : "Nothing applies to this building yet. Open Other findings to see why."
                  : "No upgrades in this category."}
              </p>
            </div>
          )}
        </div>
      </section>
      {!budgeted && sentinelBinds(plan) && (
        <p className="fineprint">
          This list may not be complete: some upgrades beyond an extremely
          high cost ceiling were not evaluated.
        </p>
      )}
      {plan.value_uplift && (
        <section className="value-uplift">
          <span className="eyebrow">PROPERTY VALUE CONTEXT</span>
          <h3>Estimated value uplift</h3>
          <Range value={plan.value_uplift.value_usd} currency />
          <p className="fineprint">
            Shown separately from energy savings. Method{" "}
            {readableText(plan.value_uplift.method)} · {plan.value_uplift.comp_count}{" "}
            comparable sales.
          </p>
          {plan.value_uplift.cap_rate && (
            <p className="fineprint">
              Capitalization rate:{" "}
              {number(plan.value_uplift.cap_rate.expected * 100, 2)}% (
              {number(plan.value_uplift.cap_rate.low * 100, 2)}–
              {number(plan.value_uplift.cap_rate.high * 100, 2)}%).
            </p>
          )}
          {plan.value_uplift.notes.map((note, i) => (
            <p className="fineprint" key={i}>
              {readableText(note)}
            </p>
          ))}
        </section>
      )}
      <div className="next-step">
        <span className="next-icon">
          <Leaf size={23} />
        </span>
        <div>
          <h3>
            {budgeted
              ? "Turn a good plan into a real project."
              : "Enter what you can spend before drafting documents."}
          </h3>
          <p>
            {budgeted
              ? "Review the scope and prepare a draft for your contractor."
              : "Contractor documents need a spending limit set first."}
          </p>
        </div>
        <button
          className="text-button"
          disabled={!budgeted}
          onClick={onDocuments}
        >
          {budgeted ? (
            <>
              Prepare documents <ArrowRight size={16} />
            </>
          ) : (
            <>
              Set a spending limit <ArrowRight size={16} />
            </>
          )}
        </button>
      </div>
    </>
  );
}
