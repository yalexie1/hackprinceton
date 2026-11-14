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
import { useState } from "react";
import type { MeasureResult, Ranged, RunResult } from "../lib/types";
import { money, number, ranged } from "../lib/format";
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
      <small>
        {ranged(value, currency)}
        {suffix}
      </small>
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
export function MeasureCard({
  measure,
  rank,
  onFocus,
}: {
  measure: MeasureResult;
  rank?: number;
  onFocus: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
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
          <p>{measure.description}</p>
          {f && (
            <>
              <div className="detail-grid">
                <div>
                  <span>Installed cost</span>
                  <Range value={f.installed_cost_usd} currency />
                </div>
                <div>
                  <span>Net upfront cash</span>
                  <Range value={f.net_upfront_usd} currency />
                </div>
                <div>
                  <span>Simple payback</span>
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
                  <span>Net present value</span>
                  <Range value={f.npv_usd} currency />
                </div>
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
                  <span>Savings-to-investment ratio</span>
                  <strong>
                    {f.sir == null ? "Not available" : number(f.sir, 2)}
                  </strong>
                </div>
                <div>
                  <span>Internal rate of return</span>
                  <strong>
                    {f.irr == null
                      ? "Not available"
                      : `${number(f.irr * 100, 1)}%`}
                  </strong>
                </div>
                <div>
                  <span>Annual O&amp;M change</span>
                  <strong>{money(f.annual_om_change_usd)}</strong>
                </div>
              </div>
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
                escalation {number(f.electricity_escalation * 100, 1)}% · gas
                escalation {number(f.gas_escalation * 100, 1)}%. Cost source:{" "}
                {f.cost_source}.
              </p>
              <div className="incentives">
                <strong>Incentives</strong>
                {f.incentives.length ? (
                  f.incentives.map((i, index) => (
                    <p key={index}>
                      {i.name} · {i.status} · {ranged(i.amount_usd, true)}
                      <small>{i.citation}</small>
                    </p>
                  ))
                ) : (
                  <p>
                    No incentive applied. Tax benefits do not reduce the upfront
                    budget.
                  </p>
                )}
              </div>
              {f.financing
                .filter((s) => s.kind === "cpace")
                .map((s, i) => (
                  <div className="finance-box" key={i}>
                    <strong>
                      C-PACE scenario ·{" "}
                      {s.eligible
                        ? "Eligible per analysis"
                        : "Eligibility unconfirmed"}
                    </strong>
                    <p>
                      {money(s.financed_usd)} financed ·{" "}
                      {s.rate == null
                        ? "Rate unavailable"
                        : `${number(s.rate * 100, 2)}%`}{" "}
                      · {s.term_years ?? "—"} years ·{" "}
                      {money(s.annual_payment_usd)} annual assessment
                    </p>
                    <p>
                      First-year net cash flow:{" "}
                      {money(s.net_cashflow_year1_usd.expected)} (
                      {ranged(s.net_cashflow_year1_usd, true)})
                    </p>
                    {s.program_sir != null && (
                      <p>
                        Program savings-to-investment ratio:{" "}
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
          {measure.flags.map((flag) => (
            <p className="inline-note" key={flag.key}>
              <Info size={14} />
              {flag.message}
            </p>
          ))}
          {measure.warnings.map((w, i) => (
            <p className="fineprint" key={i}>
              {w}
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
}: {
  run: RunResult;
  onFocus: (id: string) => void;
  onDocuments: () => void;
}) {
  const plan = run.plan;
  const [tab, setTab] = useState<"selected" | "financeable" | "skipped">(
    "selected",
  );
  if (!plan)
    return (
      <div className="empty-state">
        <Leaf />
        <h3>Your plan is taking shape</h3>
        <p>The audit will publish the ranked measures here.</p>
      </div>
    );
  return (
    <>
      <div className="metrics">
        <div className="metric featured">
          <span>
            <ArrowDownRight size={16} />
            Annual savings
          </span>
          <Range value={plan.total_annual_savings_usd} currency />
          <small>estimated each year</small>
        </div>
        <div className="metric">
          <span>
            <Coins size={16} />
            Upfront investment
          </span>
          <Range value={plan.total_upfront_usd} currency />
          <small>of {money(plan.budget_usd)} cash budget</small>
        </div>
        <div className="metric">
          <span>
            <Leaf size={16} />
            CO₂ avoided
          </span>
          <Range value={plan.total_co2_kg} suffix=" kg" />
          <small>estimated each year</small>
        </div>
      </div>
      {plan.total_upfront_usd.high > plan.budget_usd && (
        <p className="inline-note budget-warning">
          <Info size={15} />
          The plan fits at expected costs. The upper estimate may exceed your
          cash budget; confirm contractor pricing before proceeding.
        </p>
      )}
      <section className="recommendations">
        <div className="section-heading">
          <div>
            <span className="eyebrow">YOUR NEXT CHAPTER</span>
            <h2>A smarter use of your budget.</h2>
          </div>
          <span className="count-pill">{plan.selected.length} upgrades</span>
        </div>
        <p className="section-description">
          Start with no-cost changes, then prioritize annual savings. Each
          upgrade is evaluated alongside the ones already selected.
        </p>
        <div
          className="tabs"
          role="tablist"
          aria-label="Retrofit recommendations"
        >
          {(["selected", "financeable", "skipped"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
            >
              {t === "selected"
                ? "Within budget"
                : t === "financeable"
                  ? "Beyond your budget"
                  : "Not selected"}
              <span>{plan[t].length}</span>
            </button>
          ))}
        </div>
        <div className="measure-list" role="tabpanel">
          {tab === "selected" &&
            plan.selected.map((item) => (
              <MeasureCard
                key={item.measure.measure_id}
                measure={item.measure}
                rank={item.rank}
                onFocus={onFocus}
              />
            ))}
          {tab === "financeable" && (
            <>
              <p className="fineprint">
                Positive-savings measures outside the current plan. Financing
                requires separate eligibility checks.
              </p>
              {plan.financeable.map((m) => (
                <MeasureCard key={m.measure_id} measure={m} onFocus={onFocus} />
              ))}
            </>
          )}
          {tab === "skipped" &&
            plan.skipped.map((item, i) => (
              <div className="skipped-item" key={i}>
                <span>
                  <ChevronRight size={16} />
                  {run.measures.find((m) => m.measure_id === item.measure_id)
                    ?.title || item.measure_id}
                </span>
                <strong>{item.reason.replaceAll("_", " ")}</strong>
                <p>{item.detail}</p>
              </div>
            ))}
          {plan[tab].length === 0 && (
            <div className="empty-state small">
              <Check />
              <p>No measures in this category.</p>
            </div>
          )}
        </div>
      </section>
      {plan.value_uplift && (
        <section className="value-uplift">
          <span className="eyebrow">PROPERTY VALUE CONTEXT</span>
          <h3>Estimated value uplift</h3>
          <Range value={plan.value_uplift.value_usd} currency />
          <p className="fineprint">
            Shown separately from energy savings. Method{" "}
            {plan.value_uplift.method} · {plan.value_uplift.comp_count}{" "}
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
              {note}
            </p>
          ))}
        </section>
      )}
      <div className="next-step">
        <span className="next-icon">
          <Leaf size={23} />
        </span>
        <div>
          <h3>Turn a good plan into a real project.</h3>
          <p>Review the scope and prepare a draft for your contractor.</p>
        </div>
        <button className="text-button" onClick={onDocuments}>
          Prepare documents <ArrowRight size={16} />
        </button>
      </div>
    </>
  );
}
