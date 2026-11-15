import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  CheckCircle2,
  CircleHelp,
  Download,
  Info,
  Leaf,
  LoaderCircle,
  MapPin,
  Play,
  RotateCcw,
  Search,
  Settings2,
  Sparkles,
  X,
} from "lucide-react";
import type {
  PropertySummary,
  Question,
  Role,
  RunEvent,
  RunRequest,
  RunResult,
} from "./lib/types";
import { SCHEMA_VERSION } from "./lib/types";
import { api, streamRun } from "./lib/api";
import { auditStageLabel, money, number } from "./lib/format";
import Find from "./components/Find";
import Tour from "./components/Tour";
import PlanView from "./components/Plan";
import Geometry from "./components/Geometry";
import Assumptions from "./components/Assumptions";
import Documents from "./components/Documents";
import Warnings, { AuditNarrative } from "./components/Warnings";
import Calibration from "./components/Calibration";
import RunSource from "./components/RunSource";
import { AuditProgress } from "./components/AuditProgress";
import HowItWorks from "./components/HowItWorks";
import Evals from "./components/Evals";
import RoiMap from "./components/RoiMap";
import AuditTasks from "./components/AuditTasks";
import AuditMethodChoice, { type AuditMethod } from "./components/AuditMethod";
import {
  initialConnectedBudget,
  initialConnectedRole,
} from "./lib/recorded-budget";
import PropertyPreview from "./components/PropertyPreview";
import { requireRealAudit, RealAuditRequired } from "./lib/real-audit";
import WorkspaceNavigation, { publicViews, views, type View } from "./components/WorkspaceNavigation";
import { auditEventText, collapseActivity, readableText, warningText } from "./lib/homeowner-language";
import { auditIdFromUrl, auditUrl, restoreAudit } from "./lib/audit-link";
function bills(text: string): number[] | undefined {
  if (!text.trim()) return undefined;
  const values = text
    .split(/[\s,;]+/)
    .filter(Boolean)
    .map(Number);
  if (values.length !== 12 || values.some((v) => !Number.isFinite(v) || v < 0))
    throw new Error(
      "Enter exactly 12 non-negative monthly utility values, separated by commas.",
    );
  return values;
}
export default function App() {
  const demo = false;
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [connecting, setConnecting] = useState(true);
  const [serviceReady, setServiceReady] = useState(false);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [view, setView] = useState<View>("find");
  const [property, setProperty] = useState<PropertySummary | null>(null);
  const [query, setQuery] = useState("");
  const [segment, setSegment] = useState("");
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [searching, setSearching] = useState(false);
  const [budget, setBudget] = useState(15000);
  const [auditMethod, setAuditMethod] = useState<AuditMethod>("server");
  const [role, setRole] = useState<Role>("owner_occupier");
  const [electricBills, setElectricBills] = useState("");
  const [gasBills, setGasBills] = useState("");
  const [firstMonth, setFirstMonth] = useState("");
  const [desks, setDesks] = useState("");
  const [run, setRun] = useState<RunResult | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [question, setQuestion] = useState<Question | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [restoring, setRestoring] = useState(() =>
    typeof window !== "undefined" && !!auditIdFromUrl(window.location.href),
  );
  const [restored, setRestored] = useState(false);
  const [focus, setFocus] = useState<string>();
  const [help, setHelp] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const streamCursor = useRef({ id: "", count: 0 });
  useEffect(() => {
    if (!help) return;
    const previous = document.activeElement as HTMLElement | null;
    const trap = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setHelp(false);
        return;
      }
      if (event.key !== "Tab") return;
      const elements = Array.from(
        document.querySelectorAll<HTMLElement>(
          ".help-modal button:not(:disabled), .help-modal a[href], .help-modal input",
        ),
      );
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [help]);
  const done = run?.status === "done";
  const office = property?.segment === "commercial";
  const budgets: number[] = [];
  function clearAsync() {
    epoch.current++;
    controller.current?.abort();
  }
  useEffect(
    () => () => {
      epoch.current++;
      controller.current?.abort();
    },
    [],
  );
  useEffect(() => {
    document.title = `${view === "find" ? "Your properties" : views.find((v) => v.id === view)?.label || "Building audit"} — Leto`;
  }, [view]);
  useEffect(() => {
    if (!serviceReady) {
      setProperties([]);
      return;
    }
    const abort = new AbortController();
    setSearching(true);
    const timeout = setTimeout(() => {
      void api
        .search(query, segment, abort.signal)
        .then(setProperties)
        .catch((e) => {
          if (!abort.signal.aborted) setError(e.message);
        })
        .finally(() => {
          if (!abort.signal.aborted) setSearching(false);
        });
    }, 250);
    return () => {
      clearTimeout(timeout);
      abort.abort();
    };
  }, [serviceReady, query, segment]);
  useEffect(() => {
    if (view !== "documents") setNotice("");
  }, [view]);
  useEffect(() => {
    let cancelled = false;
    setConnecting(true);
    setServiceReady(false);
    setError("");
    void api
      .health()
      .then((health) => {
        if (cancelled) return;
        if (health.schema_version !== SCHEMA_VERSION)
          throw new Error(
            "The building service has been updated. Refresh the app before continuing.",
          );
        setServiceReady(true);
      })
      .catch((error: unknown) => {
        if (!cancelled) setRestoring(false);
        if (!cancelled)
          setError(
            error instanceof Error &&
              error.message.startsWith("The building service")
              ? error.message
              : "We couldn’t connect to the building service. Try the connection again in a moment.",
          );
      })
      .finally(() => {
        if (!cancelled) setConnecting(false);
      });
    return () => {
      cancelled = true;
    };
  }, [connectionAttempt]);
  useEffect(() => {
    if (!serviceReady) return;
    const id = auditIdFromUrl(window.location.href);
    if (!id) return;
    const current = epoch.current;
    const abort = new AbortController();
    controller.current = abort;
    let cancelled = false;
    setRestoring(true);
    void restoreAudit(id, AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]))
      .then((result) => {
        if (cancelled || current !== epoch.current) return;
        setProperty(result.property);
        setRun(result);
        setBudget(result.request.budget_usd);
        setRole(result.request.role);
        setEvents([]);
        setQuestion(result.status === "waiting_for_user" ? result.questions[0] || null : null);
        setRestored(true);
        setView(result.status === "done" ? "plan" : "audit");
        if (result.status === "error")
          setError(result.warnings.join(" ") || "This earlier audit did not complete. No new analysis was started.");
      })
      .catch((error: unknown) => {
        if (cancelled || current !== epoch.current) return;
        setError(error instanceof RealAuditRequired ? error.message :
          "We couldn’t reopen this audit. Its files may still be saved, but this service cannot currently retrieve it. Browse properties or retry the link when recovery is available. No new analysis was started.");
      })
      .finally(() => {
        if (!cancelled && current === epoch.current) setRestoring(false);
      });
    return () => { cancelled = true; abort.abort(); };
  }, [serviceReady]);
  useEffect(() => {
    if (run) window.history.replaceState(null, "", auditUrl(window.location.href, run.run_id));
  }, [run?.run_id]);
  function navigate(v: View) {
    if (!publicViews.has(v) && !done) return;
    setView(v);
    setError("");
  }
  function choose(p: PropertySummary) {
    clearAsync();
    window.history.replaceState(null, "", auditUrl(window.location.href, null));
    setRestored(false);
    setRestoring(false);
    setProperty(p);
    setRun(null);
    setQuestion(null);
    setEvents([]);
    setBusy(false);
    setError("");
    setView("setup");
    setRole(initialConnectedRole(p.sid));
    setBudget(initialConnectedBudget(p.sid));
    setElectricBills("");
    setGasBills("");
    setFirstMonth("");
    setDesks("");
  }
  async function watch(id: string, current: number) {
    const abort = new AbortController();
    controller.current = abort;
    try {
      const snapshot = await api.result(id);
      if (current !== epoch.current || abort.signal.aborted) return;
      requireRealAudit(snapshot, property!.sid);
      const completed =
        snapshot.status === "done" || snapshot.status === "error";
      if (streamCursor.current.id !== id)
        streamCursor.current = { id, count: 0 };
      await streamRun(
        id,
        (event) => {
          if (current !== epoch.current) return;
          streamCursor.current.count++;
          setEvents((previous) => [...previous, event]);
          if (event.type === "question" && !completed) {
            const q = (event.payload.question ||
              event.payload) as unknown as Question;
            if (q.id && q.choices) setQuestion(q);
          }
          // Tool errors can be recoverable even without an explicit payload flag.
          // The final RunResult status decides whether the audit failed.
        },
        abort.signal,
        { afterEvents: streamCursor.current.count, followToEnd: completed },
      );
      if (current !== epoch.current) return;
      const result = await api.result(id);
      if (current !== epoch.current) return;
      requireRealAudit(result, property!.sid);
      setRun(result);
      setBudget(result.request.budget_usd);
      if (result.status === "waiting_for_user")
        setQuestion(result.questions[0] || null);
      else setQuestion(null);
      if (result.status === "running")
        throw new Error(
          "The audit stream ended before completion. Reconnect to continue following this run.",
        );
      if (result.status === "error")
        setError(result.warnings.join(" ") || "The audit could not complete.");
    } catch (e) {
      if (current === epoch.current && !abort.signal.aborted) {
        if (e instanceof RealAuditRequired) {
          setRun(null);
          setEvents([]);
          setQuestion(null);
          setView("setup");
        }
        setError(
          e instanceof Error
            ? e.message
            : "The audit connection was interrupted.",
        );
      }
    } finally {
      if (current === epoch.current) setBusy(false);
    }
  }
  async function start(event?: React.FormEvent) {
    event?.preventDefault();
    if (!property || busy) return;
    clearAsync();
    const current = epoch.current;
    setError("");
    setNotice("");
    setRestored(false);
    setBusy(true);
    setQuestion(null);
    setEvents([]);
    try {
      if (!Number.isFinite(budget) || budget < 0)
        throw new Error("Enter a valid non-negative cash budget.");
      const electricity = demo ? undefined : bills(electricBills);
      const gas = demo ? undefined : bills(gasBills);
      if (gas && !electricity)
        throw new Error(
          "Add 12 electricity readings before adding gas readings.",
        );
      if (
        electricity &&
        firstMonth &&
        !/^\d{4}-(0[1-9]|1[0-2])$/.test(firstMonth)
      )
        throw new Error("Choose a valid first billing month.");
      if (
        !demo &&
        desks &&
        (!Number.isInteger(Number(desks)) || Number(desks) < 1)
      )
        throw new Error("Enter a positive whole number of desks.");
      const request: RunRequest = {
        sid: property.sid,
        budget_usd: budget,
        role,
        ...(!demo && auditMethod === "analysis"
          ? { mode: "analysis" as const }
          : {}),
        ...(!demo && desks ? { desks_requested: Number(desks) } : {}),
        ...(electricity
          ? {
              bills: {
                electricity_kwh: electricity,
                ...(firstMonth ? { first_month: firstMonth } : {}),
                ...(gas ? { gas_kwh: gas } : {}),
              },
            }
          : {}),
      };
      const { run_id } = await api.start(request);
      if (current !== epoch.current) return;
      setRun({
        schema_version: SCHEMA_VERSION,
        run_id,
        status: "running",
        request,
        property,
        measures: [],
        questions: [],
        narrative_md: "",
        warnings: [],
      });
      setView("audit");
      void watch(run_id, current);
    } catch (e) {
      if (current === epoch.current) {
        setError(e instanceof Error ? e.message : "Could not start the audit.");
        setBusy(false);
      }
    }
  }
  async function answer(value: unknown) {
    if (!run || !question || busy) return;
    setError("");
    setBusy(true);
    const current = epoch.current;
    try {
      await api.answer(run.run_id, question.id, value);
      if (current !== epoch.current) return;
      setRestored(false);
      setQuestion(null);
      setRun({ ...run, status: "running", questions: [] });
      void watch(run.run_id, current);
    } catch (e) {
      if (current === epoch.current) {
        setError(
          e instanceof Error ? e.message : "Could not submit the answer.",
        );
        setBusy(false);
      }
    }
  }
  async function update(changes: {
    budget_usd?: number;
    overrides?: Record<string, string | number | boolean>;
  }) {
    if (!run || busy) return;
    setError("");
    if (
      changes.budget_usd != null &&
      (!Number.isFinite(changes.budget_usd) || changes.budget_usd < 0)
    ) {
      setError("Enter a valid non-negative budget.");
      return;
    }
    clearAsync();
    const current = epoch.current;
    setBusy(true);
    try {
      await api.update(run.run_id, changes);
      if (current !== epoch.current) return;
      setRestored(false);
      setRun({ ...run, status: "running", questions: [] });
      setQuestion(null);
      setView("audit");
      void watch(run.run_id, current);
    } catch (e) {
      if (current === epoch.current) {
        setError(
          e instanceof Error ? e.message : "Could not update the audit.",
        );
        setBusy(false);
      }
    }
  }
  const resultViews: View[] = [
    "plan",
    "roof",
    "layout",
    "assumptions",
    "documents",
  ];
  const questionEvent = [...events]
    .reverse()
    .find(
      (event) =>
        event.type === "question" &&
        ((event.payload.question || event.payload) as Partial<Question>).id ===
          question?.id,
    );
  const approval =
    questionEvent?.payload.kind === "approval"
      ? (questionEvent.payload.approval as Record<string, unknown> | undefined)
      : undefined;
  return (
    <div className="app-shell horizontal-workspace">
      <div className="main-shell">
        <WorkspaceNavigation
          view={view}
          complete={done}
          hasRun={!!run}
          busy={busy}
          needsInput={!!question}
          propertyName={run?.property.name || property?.name}
          onNavigate={(next) => {
            if (next === "audit" && run) setView("audit");
            else navigate(next);
          }}
        >
          <div className="connection-state" role="status">
            <span className={`status-dot ${serviceReady ? "" : "pending"}`} />
            {connecting ? "Connecting…" : serviceReady ? "Building service connected" : "Connection needed"}
            {!connecting && !serviceReady && (
              <button onClick={() => setConnectionAttempt((attempt) => attempt + 1)}>Try again</button>
            )}
          </div>
        </WorkspaceNavigation>
        <main>
          {restoring && <p className="inline-note" role="status"><LoaderCircle className="spin" size={18} /> Reopening your existing audit…</p>}
          {restored && (
            <p className="inline-note" role="status">
              Reopened your existing audit. Results are from the original calculation; no new analysis was started.
              {events.length === 0 && " Earlier activity has not been loaded on this page."}
            </p>
          )}
          <div className={`mode-notice ${demo ? "" : "live"}`}>
            <span className="status-dot" />
            YOUR HOME, UNDERSTOOD
            <span>
              See what improvements could cost, save and change for your home.
            </span>
            <button
              onClick={() => setHelp(true)}
              aria-label="About this workspace"
            >
              <Info size={15} />
            </button>
          </div>
          {error && (
            <div className="error-message" role="alert">
              <Info size={18} />
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <p className="success-message" role="status">
              {notice}
            </p>
          )}
          {view === "how" && <HowItWorks onExplore={navigate} />}
          {view === "evals" && <Evals />}
          {view === "solar-map" && <RoiMap />}
          {view === "find" && !restoring && (
            <Find
              properties={properties}
              query={query}
              setQuery={setQuery}
              segment={segment}
              setSegment={setSegment}
              loading={connecting || searching}
              demo={demo}
              onSelect={choose}
            />
          )}
          {view === "setup" && property && (
            <>
              <button className="back-button" onClick={() => setView("find")}>
                <ArrowLeft size={15} />
                All properties
              </button>
              <div className="setup-grid">
                <section>
                  <span className="eyebrow">
                    A PLAN THAT FITS YOUR BUILDING
                  </span>
                  <h1>Set up your energy audit.</h1>
                  <p className="section-description">
                    Tell us your budget and whether you own or rent. We’ll show
                    which improvements could make sense for you.
                  </p>
                  <div className="setup-property">
                    <div className="setup-actual-photo">
                      <PropertyPreview
                        property={property}
                        allowListedLocation
                      />
                    </div>
                    <div>
                      <h3>{property.name}</h3>
                      <p>
                        <MapPin size={14} />
                        {property.city}, {property.state}
                      </p>
                    </div>
                  </div>
                </section>
                <form className="setup-form" onSubmit={start}>
                  <div className="card-heading">
                    <div>
                      <Sparkles size={18} />
                      <span>Set up your energy audit</span>
                    </div>
                    <span className="step-label">Your preferences</span>
                  </div>
                  {!demo && (
                    <AuditMethodChoice
                      value={auditMethod}
                      onChange={setAuditMethod}
                    />
                  )}
                  <label>
                    Upfront cash budget
                    {demo ? (
                      <select
                        value={budget}
                        onChange={(e) => setBudget(Number(e.target.value))}
                      >
                        {budgets.map((b) => (
                          <option key={b} value={b}>
                            {money(b)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <div className="currency-input">
                        <span>$</span>
                        <input
                          aria-label="Upfront cash budget"
                          required
                          type="number"
                          min="0"
                          step="100"
                          value={Number.isNaN(budget) ? "" : budget}
                          onChange={(e) =>
                            setBudget(
                              e.target.value === ""
                                ? NaN
                                : Number(e.target.value),
                            )
                          }
                        />
                      </div>
                    )}
                    <small>
                      {demo
                        ? "Saved budget scenarios are available in demo mode."
                        : "A hard cap on expected upfront cash. Later tax benefits do not reduce this cap."}
                    </small>
                  </label>
                  <label>
                    Your role
                    <select
                      value={role}
                      disabled={demo}
                      onChange={(e) => setRole(e.target.value as Role)}
                    >
                      <option value="owner_occupier">
                        I own and use this property
                      </option>
                      <option value="landlord">I own it and rent it out</option>
                      <option value="tenant">I rent this property</option>
                    </select>
                    <small>
                      {demo
                        ? "The saved example fixes this role. All roles are available in live mode."
                        : "Recommendations reflect the changes you’re authorized to make."}
                    </small>
                  </label>
                  {!demo && (
                    <details className="bills-form">
                      <summary>
                        Add utility history <span>Optional</span>
                      </summary>
                      <p>
                        Enter twelve consecutive months, separated by commas.
                        Leave the first month blank for January through
                        December.
                      </p>
                      <label>
                        First billing month (optional)
                        <input
                          type="month"
                          value={firstMonth}
                          onChange={(event) =>
                            setFirstMonth(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        Electricity use (kWh, 12 months)
                        <textarea
                          rows={3}
                          value={electricBills}
                          onChange={(e) => setElectricBills(e.target.value)}
                          placeholder="1200, 1100, 1000, …"
                        />
                      </label>
                      <label>
                        Gas use (kWh thermal, 12 months)
                        <textarea
                          rows={3}
                          value={gasBills}
                          onChange={(e) => setGasBills(e.target.value)}
                          placeholder="Optional, same month order"
                        />
                      </label>
                    </details>
                  )}
                  {!demo && office && (
                    <label>
                      Desk positions requested (optional)
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={desks}
                        onChange={(event) => setDesks(event.target.value)}
                        placeholder="Number of desks"
                      />
                    </label>
                  )}
                  <div className="audit-includes">
                    <span>
                      <Check size={15} />
                      Current energy use
                    </span>
                    <span>
                      <Check size={15} />
                      Recommended improvements
                    </span>
                    <span>
                      <Check size={15} />
                      Costs, savings &amp; evidence
                    </span>
                  </div>
                  <button className="primary-button wide" disabled={busy}>
                    {busy ? (
                      <LoaderCircle className="spin" size={17} />
                    ) : (
                      <Sparkles size={17} />
                    )}{" "}
                    {demo
                      ? "Explore demo audit"
                      : auditMethod === "analysis"
                        ? "Calculate my plan"
                        : "Start energy audit"}
                    <ArrowRight size={17} />
                  </button>
                  <p className="fineprint">
                    {demo
                      ? "Review the property’s saved audit."
                      : auditMethod === "analysis"
                        ? "Uses your property’s records and preferences to estimate improvements. Review what was measured and what still needs checking."
                        : "You may be asked up to three questions if an uncertain input changes the plan."}
                  </p>
                </form>
              </div>
            </>
          )}
          {view === "audit" && run && (
            <>
              <div className="page-title">
                <div>
                  <span className="eyebrow">YOUR ENERGY AUDIT</span>
                  <h1>
                    {done
                      ? "Your energy audit is ready."
                      : question
                        ? "A question about your building."
                        : "Analyzing your building."}
                  </h1>
                  <p>
                    {run.property.name} · {money(run.request.budget_usd)} cash
                    budget
                  </p>
                  <RunSource run={run} restored={restored} />
                  <AuditProgress
                    events={events}
                    done={done}
                    waiting={Boolean(question)}
                  />
                </div>
                {done && (
                  <button
                    className="primary-button"
                    onClick={() => setView("plan")}
                  >
                    Explore your plan
                    <ArrowRight size={16} />
                  </button>
                )}
              </div>
              {/* The question sits above the log: in a rehearsal it was below a
                  screenful of events, so the one thing the run needed from a person was
                  the last thing they saw. */}
              {question && (
                <div className="question-card">
                  <span className="eyebrow">
                    {approval
                      ? "YOUR APPROVAL IS REQUIRED"
                      : "A QUICK QUESTION"}
                  </span>
                  <h3>{readableText(question.prompt)}</h3>
                  <p>{readableText(question.impact_note)}</p>
                  {approval && (
                    <p className="inline-note">
                      Draft request:{" "}
                      {String(approval.doc_type || "document").replaceAll(
                        "_",
                        " ",
                      )}{" "}
                      · {String(approval.state || "jurisdiction pending")}
                      <br />
                      Scope:{" "}
                      {Array.isArray(approval.measure_ids)
                        ? approval.measure_ids
                            .map(
                              (id) =>
                                run.plan?.selected.find(
                                  (item) => item.measure.measure_id === id,
                                )?.measure.title ||
                                run.measures.find(
                                  (measure) => measure.measure_id === id,
                                )?.title ||
                                String(id),
                            )
                            .join(", ")
                        : "Review the scope before approving."}
                    </p>
                  )}
                  {demo && (
                    <p className="fineprint">
                      Demo replay: your choice advances the saved scenario. Its
                      estimates and original answers remain unchanged.
                    </p>
                  )}
                  <div>
                    {question.choices.map((choice, i) => (
                      <button
                        className="secondary-button"
                        disabled={busy}
                        key={i}
                        onClick={() => void answer(choice.value)}
                      >
                        {readableText(choice.label)}
                        <ArrowRight size={14} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="audit-grid">
                <section className="audit-timeline">
                  <div className="card-heading">
                    <div>
                      <Sparkles size={17} />
                      <span>How we built your plan</span>
                    </div>
                    <span className="count-pill">
                      {done
                        ? "Complete"
                        : question
                          ? "Needs your input"
                          : busy
                            ? "In progress"
                            : "Disconnected"}
                    </span>
                  </div>
                  <div
                    className="event-list"
                    aria-live="polite"
                    aria-relevant="additions"
                  >
                    {collapseActivity(
                      events,
                      (e) => `${e.type}|${auditStageLabel(e.stage || e.type)}|${auditEventText(e)}`,
                    ).map(({ event, count, index: i }) => (
                      <div className={`event ${event.type}`} key={i}>
                        <span className="event-dot">
                          {event.type === "fallback" ||
                          event.type === "error" ? (
                            <Info size={14} />
                          ) : event.type === "question" ? (
                            <CircleHelp size={14} />
                          ) : (
                            <Check size={14} />
                          )}
                        </span>
                        <div>
                          <small>
                            {auditStageLabel(event.stage || event.type)}
                          </small>
                          <p>
                            {auditEventText(event)}
                            {count > 1 && (
                              <span className="event-count"> ({count} steps)</span>
                            )}
                          </p>
                          {!done &&
                            i === events.length - 1 &&
                            event.type === "todo" &&
                            typeof event.payload.done === "number" &&
                            typeof event.payload.total === "number" &&
                            event.payload.total > 0 && (
                              <progress
                                aria-label="Audit task progress"
                                value={event.payload.done}
                                max={event.payload.total}
                              />
                            )}
                          {typeof event.payload.detail === "string" &&
                            !event.message.includes(event.payload.detail) && (
                              <details>
                                <summary>Data source detail</summary>
                                <p>{warningText(event.payload.detail)}</p>
                              </details>
                            )}
                          {event.type === "todo" && (
                            <AuditTasks
                              event={event}
                              finished={done}
                              archived={i < events.length - 1}
                            />
                          )}
                        </div>
                      </div>
                    ))}
                    {busy && (
                      <div className="audit-working">
                        <LoaderCircle className="spin" size={17} />
                        {demo
                          ? "Loading the next part of your scenario…"
                          : "Waiting for the agent’s next update…"}
                      </div>
                    )}
                  </div>
                  {!busy && !done && !question && !demo && (
                    <button
                      className="secondary-button reconnect"
                      onClick={() => {
                        clearAsync();
                        setBusy(true);
                        setError("");
                        void watch(run.run_id, epoch.current);
                      }}
                    >
                      <RotateCcw size={15} />
                      Reconnect to this audit
                    </button>
                  )}
                  {done && <Calibration run={run} />}
                </section>
                <Tour
                  key={run.property.sid}
                  sid={run.property.sid}
                  office={!!office}
                  demo={demo}
                  measures={run.measures}
                  plan={run.plan}
                  run={run}
                />
              </div>
            </>
          )}
          {resultViews.includes(view) && run && done && (
            <>
              <div className="page-title">
                <div>
                  <button
                    className="back-button"
                    onClick={() => setView("find")}
                  >
                    <ArrowLeft size={14} />
                    All properties
                  </button>
                  <h1>{run.property.name}</h1>
                  <p>
                    <MapPin size={14} />
                    {[run.property.city, run.property.state]
                      .filter(Boolean)
                      .join(", ")}
                    <span className="title-divider" />{" "}
                    {office ? "Commercial office" : "Residential home"}
                    <span className="title-divider" />{" "}
                    <span className="completed-label">
                      <CheckCircle2 size={13} />
                      Audit complete
                    </span>
                  </p>
                  <RunSource run={run} restored={restored} />
                </div>
                <button
                  className="secondary-button"
                  disabled={exporting}
                  onClick={async () => {
                    setExporting(true);
                    setExportError("");
                    try {
                      const { exportAuditPdf } = await import("./lib/report-pdf");
                      await exportAuditPdf(run);
                    } catch {
                      setExportError("The PDF could not be created. Please try exporting again.");
                    } finally { setExporting(false); }
                  }}
                >
                  <Download size={16} />
                  {exporting ? "Creating PDF…" : "Export report (PDF)"}
                </button>
              </div>
              {exportError && <p className="inline-note" role="alert">{exportError}</p>}
              <div className={`result-grid ${view === "roof" ? "roof-result-grid" : ""}`}>
                <div className="result-main">
                  {/* The audit's own account of the building, in the main column: it
                      explains the numbers beside it, so it reads before them rather than
                      beside them in a sidebar. */}
                  {view !== "roof" && <section className="insight-card insight-main">
                    <Sparkles size={19} />
                    <span className="eyebrow">
                      {demo ? "SAVED EXAMPLE REPORT" : "THE AUDIT’S TAKE"}
                    </span>
                    {demo && (
                      <p className="fineprint">
                        This is a saved example report. Answering replay
                        questions does not recalculate its numbers.
                      </p>
                    )}
                    <AuditNarrative
                      text={run.narrative_md}
                      warnings={run.warnings}
                      concise
                    />
                    <button
                      className="text-button"
                      onClick={() => setView("assumptions")}
                    >
                      See the assumptions
                      <ArrowRight size={14} />
                    </button>
                  </section>}
                  {view === "plan" && (
                    <>
                      <Calibration run={run} />
                      <PlanView
                        run={run}
                        onFocus={setFocus}
                        onDocuments={() => setView("documents")}
                      />
                    </>
                  )}{" "}
                  {view === "roof" && <Geometry run={run} demo={demo} />}{" "}
                  {view === "layout" && (
                    <Geometry run={run} demo={demo} layout />
                  )}{" "}
                  {view === "assumptions" && (
                    <Assumptions
                      run={run}
                      demo={demo}
                      busy={busy}
                      onSave={(key, value) =>
                        void update({ overrides: { [key]: value } })
                      }
                    />
                  )}{" "}
                  {view === "documents" && (
                    <Documents key={run.run_id} run={run} demo={demo} />
                  )}
                </div>
                <aside className="result-aside">
                  <Tour
                    key={run.property.sid}
                    sid={run.property.sid}
                    office={!!office}
                    demo={demo}
                    measures={run.measures}
                    plan={run.plan}
                    run={run}
                    focus={focus}
                  />
                  <section className="budget-card">
                    <div className="card-heading">
                      <div>
                        <Settings2 size={16} />
                        <span>Your budget</span>
                      </div>
                    </div>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void update({ budget_usd: budget });
                      }}
                    >
                      <label>
                        Cash budget
                        {demo ? (
                          <select
                            value={budget}
                            disabled={budgets.length === 1}
                            onChange={(e) => {
                              const b = Number(e.target.value);
                              setBudget(b);
                              void update({ budget_usd: b });
                            }}
                          >
                            {budgets.map((b) => (
                              <option key={b} value={b}>
                                {money(b)}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            type="number"
                            min="0"
                            required
                            value={Number.isNaN(budget) ? "" : budget}
                            onChange={(e) =>
                              setBudget(
                                e.target.value === ""
                                  ? NaN
                                  : Number(e.target.value),
                              )
                            }
                          />
                        )}
                      </label>
                      {!demo && (
                        <button
                          className="secondary-button wide"
                          disabled={busy}
                        >
                          <RotateCcw size={14} />
                          {run.served_by === "replay"
                            ? "Update budget"
                            : "Update plan"}
                        </button>
                      )}
                      <small>
                        {demo
                          ? budgets.length === 1
                            ? "This example has one saved budget. A live analysis is needed to compare a different budget."
                            : "Switch between saved budget scenarios."
                          : run.served_by === "replay"
                            ? "Changing your budget checks the saved plan again. Review any notes before deciding."
                            : "Changing your budget recalculates the plan."}
                      </small>
                    </form>
                    <p className="budget-rule">
                      <CheckCircle2 size={14} />
                      Operations first. Solar last.
                    </p>
                  </section>
                  {run.baseline && (
                    <section className="baseline-card">
                      <span className="eyebrow">BEFORE IMPROVEMENTS</span>
                      <h3>
                        {money(run.baseline.annual.cost_usd.expected)}
                        <small> / year</small>
                      </h3>
                      <p>
                        {money(run.baseline.annual.cost_usd.low)}–
                        {money(run.baseline.annual.cost_usd.high)} estimated
                        energy cost
                      </p>
                      <div
                        className="spark-bars"
                        aria-label="Monthly electricity use in kilowatt-hours"
                      >
                        {run.baseline.monthly_electricity_kwh.map((v, i) => (
                          <div
                            key={i}
                            style={{
                              height: `${Math.max(3, (v / Math.max(...run.baseline!.monthly_electricity_kwh, 1)) * 65)}px`,
                            }}
                            title={`${new Date(2026, i, 1).toLocaleString("en-US", { month: "short" })}: ${number(v)} kWh`}
                          />
                        ))}
                      </div>
                      <div className="chart-labels">
                        <span>JAN</span>
                        <span>JUN</span>
                        <span>DEC</span>
                      </div>
                      <small>
                        {run.baseline.calibrated_to_bills
                          ? "Checked against your utility bills"
                          : "Not checked against utility bills yet"}
                      </small>
                    </section>
                  )}
                </aside>
              </div>
              <Warnings
                warnings={[
                  ...run.warnings,
                  ...(run.baseline?.warnings || []),
                  ...events
                    .filter(
                      (event) =>
                        event.type === "fallback" || event.type === "error",
                    )
                    .map(
                      (event) =>
                        event.message ||
                        String(
                          event.payload.detail || event.payload.fallback || "",
                        ),
                    ),
                ]}
              />
            </>
          )}
          <footer className="app-footer">
            <span>
              <Leaf size={13} />
              Built for a lighter footprint.
            </span>
            <span>
              HackPrinceton 2026 <span>↗</span>
            </span>
          </footer>
        </main>
      </div>
      {help && (
        <div className="modal-backdrop" onClick={() => setHelp(false)}>
          <section
            className="help-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="help-title"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setHelp(false);
            }}
          >
            <button
              autoFocus
              className="icon-button modal-close"
              aria-label="Close help"
              onClick={() => setHelp(false)}
            >
              <X size={20} />
            </button>
            <span className="brand-mark">
              <Leaf size={25} />
            </span>
            <span className="eyebrow">A CLEARER WAY FORWARD</span>
            <h2 id="help-title">Understand. Improve. Act.</h2>
            <ol>
              <li>
                <strong>Choose a building.</strong>
                <p>Find a scanned home or office in the supported cities.</p>
              </li>
              <li>
                <strong>Explore the audit.</strong>
                <p>
                  Review the assumptions, evidence, and a retrofit plan that
                  fits your budget.
                </p>
              </li>
              <li>
                <strong>Prepare the next step.</strong>
                <p>Compare options and review a contractor document draft.</p>
              </li>
            </ol>
            <div className="inline-note">
              <Info size={17} />
              <span>
                Your plan explains where its numbers came from and whether it is
                a saved audit or a new calculation. Savings are estimates.
                Confirm the building details and get a contractor’s quote before
                starting work.
              </span>
            </div>
            <button
              className="primary-button wide"
              onClick={() => setHelp(false)}
            >
              Let’s explore
              <ArrowRight size={16} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
