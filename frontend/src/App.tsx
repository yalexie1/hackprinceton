import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Box,
  Building2,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Download,
  FileText,
  Home,
  Info,
  Layers3,
  Leaf,
  LoaderCircle,
  MapPin,
  PanelLeftClose,
  Play,
  RotateCcw,
  Search,
  Settings2,
  Sparkles,
  Sun,
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
import {
  demoBudgets,
  demoEvents,
  demoProperties,
  demoQuestion,
  demoRun,
  demoStages,
} from "./lib/fixtures";
import { download, money, number } from "./lib/format";
import Find from "./components/Find";
import HouseViewer from "./components/HouseViewer";
import Tour from "./components/Tour";
import PlanView from "./components/Plan";
import Geometry from "./components/Geometry";
import Assumptions from "./components/Assumptions";
import Documents from "./components/Documents";
import Warnings, { AuditNarrative } from "./components/Warnings";
type View =
  | "find"
  | "setup"
  | "audit"
  | "plan"
  | "roof"
  | "layout"
  | "assumptions"
  | "documents";
const views: { id: View; label: string; icon: typeof Home }[] = [
  { id: "find", label: "Properties", icon: Home },
  { id: "plan", label: "Energy plan", icon: ClipboardList },
  { id: "roof", label: "Solar & roof", icon: Sun },
  { id: "layout", label: "Workspace", icon: Layers3 },
  { id: "assumptions", label: "Assumptions", icon: Settings2 },
  { id: "documents", label: "Documents", icon: FileText },
];
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
  const [demo, setDemo] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [view, setView] = useState<View>("find");
  const [property, setProperty] = useState<PropertySummary | null>(null);
  const [query, setQuery] = useState("");
  const [segment, setSegment] = useState("");
  const [properties, setProperties] =
    useState<PropertySummary[]>(demoProperties);
  const [searching, setSearching] = useState(false);
  const [budget, setBudget] = useState(15000);
  const [role, setRole] = useState<Role>("owner_occupier");
  const [electricBills, setElectricBills] = useState("");
  const [gasBills, setGasBills] = useState("");
  const [run, setRun] = useState<RunResult | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [question, setQuestion] = useState<Question | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [focus, setFocus] = useState<string>();
  const [mobileNav, setMobileNav] = useState(false);
  const [help, setHelp] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const epoch = useRef(0);
  const savedRun = useRef<RunResult | null>(null);
  const step = useRef(0);
  const replay = useRef<RunEvent[]>(demoStages);
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
  const budgets = demoBudgets(property?.sid);
  function clearAsync() {
    epoch.current++;
    controller.current?.abort();
    if (timer.current) clearTimeout(timer.current);
  }
  useEffect(
    () => () => {
      epoch.current++;
      controller.current?.abort();
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  useEffect(() => {
    document.title = `${view === "find" ? "Your properties" : views.find((v) => v.id === view)?.label || "Building audit"} — Evergreen`;
  }, [view]);
  useEffect(() => {
    if (demo) {
      setProperties(
        demoProperties.filter(
          (p) =>
            (!segment || p.segment === segment) &&
            `${p.name} ${p.city} ${p.address}`
              .toLowerCase()
              .includes(query.toLowerCase()),
        ),
      );
      setSearching(false);
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
  }, [demo, query, segment]);
  useEffect(() => {
    if (view !== "documents") setNotice("");
  }, [view]);
  async function switchMode(nextDemo: boolean) {
    if (nextDemo === demo || connecting) return;
    setError("");
    if (!nextDemo) {
      setConnecting(true);
      try {
        const health = await api.health();
        if (health.schema_version !== SCHEMA_VERSION)
          throw new Error(
            `Backend schema ${health.schema_version} differs from this frontend’s ${SCHEMA_VERSION} contract. Update the frontend adapter before connecting.`,
          );
      } catch (e) {
        setError(
          e instanceof Error && e.message.startsWith("Backend schema")
            ? e.message
            : "Could not connect to the compatible backend at /api/health. Start the FastAPI server on port 8000, or configure VITE_API_BASE_URL. Demo mode remains available.",
        );
        setConnecting(false);
        return;
      }
      setConnecting(false);
    }
    clearAsync();
    setDemo(nextDemo);
    setView("find");
    setProperty(null);
    setRun(null);
    setQuestion(null);
    setEvents([]);
    setProperties(nextDemo ? demoProperties : []);
    setBusy(false);
    setRole("owner_occupier");
    setQuery("");
    setSegment("");
    setElectricBills("");
    setGasBills("");
  }
  function navigate(v: View) {
    if (v !== "find" && !done) return;
    setView(v);
    setMobileNav(false);
    setError("");
  }
  function choose(p: PropertySummary) {
    clearAsync();
    setProperty(p);
    setRun(null);
    setQuestion(null);
    setEvents([]);
    setBusy(false);
    setError("");
    setView("setup");
    const options = demoBudgets(p.sid);
    setRole(demo ? demoRun(p.sid, options[0]).request.role : "owner_occupier");
    setBudget(demo ? (options.includes(15000) ? 15000 : options[0]) : 15000);
    setElectricBills("");
    setGasBills("");
  }
  function pumpDemo() {
    const current = epoch.current;
    timer.current = setTimeout(() => {
      if (current !== epoch.current) return;
      const event = replay.current[step.current++];
      if (!event) return;
      setEvents((previous) => [...previous, event]);
      if (event.type === "question") {
        const q = (event.payload.question ||
          event.payload) as unknown as Question;
        const pending = q.id && q.choices ? q : demoQuestion;
        setQuestion(pending);
        setBusy(false);
        setRun(
          (previous) =>
            previous && {
              ...previous,
              status: "waiting_for_user",
              questions: [pending],
            },
        );
        return;
      }
      if (event.type === "done") {
        setRun(savedRun.current);
        setBusy(false);
        return;
      }
      pumpDemo();
    }, 300);
  }
  async function watch(id: string, current: number) {
    const abort = new AbortController();
    controller.current = abort;
    try {
      const snapshot = await api.result(id);
      if (current !== epoch.current || abort.signal.aborted) return;
      const completed = snapshot.status === "done" || snapshot.status === "error";
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
      if (current === epoch.current && !abort.signal.aborted)
        setError(
          e instanceof Error
            ? e.message
            : "The audit connection was interrupted.",
        );
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
      const request: RunRequest = {
        sid: property.sid,
        budget_usd: budget,
        role,
        ...(electricity
          ? {
              bills: {
                electricity_kwh: electricity,
                ...(gas ? { gas_kwh: gas } : {}),
              },
            }
          : {}),
      };
      if (demo) {
        const result = demoRun(property.sid, budget);
        savedRun.current = result;
        replay.current = demoEvents(property.sid);
        setRun({
          ...result,
          status: "running",
          plan: null,
          measures: [],
          baseline: null,
          building_model: null,
        });
        setView("audit");
        step.current = 0;
        pumpDemo();
      } else {
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
      }
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
    if (demo) {
      setQuestion(null);
      setBusy(true);
      setRun({ ...run, status: "running", questions: [] });
      setEvents((previous) => [
        ...previous,
        {
          type: "stage_done",
          stage: "assumptions",
          message:
            "Answer recorded for the demo replay. The saved example estimates are unchanged.",
          payload: {},
        },
      ]);
      pumpDemo();
      return;
    }
    setBusy(true);
    const current = epoch.current;
    try {
      await api.answer(run.run_id, question.id, value);
      if (current !== epoch.current) return;
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
    if (demo) {
      const result = demoRun(run.property.sid, changes.budget_usd || budget);
      setRun(result);
      setBudget(result.request.budget_usd);
      setNotice("Showing the saved scenario for this budget.");
      return;
    }
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
  const title =
    views.find((v) => v.id === view)?.label ||
    (view === "setup" ? "Set up your audit" : "Building audit");
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "is-open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            setView("find");
            setMobileNav(false);
          }}
        >
          <span className="brand-mark">
            <Box size={23} strokeWidth={1.7} />
          </span>
          <span>
            evergreen<span>BUILDING INTELLIGENCE</span>
          </span>
        </a>
        <button
          className="mobile-close icon-button"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        >
          <X size={20} />
        </button>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav aria-label="Main navigation">
          {views.map((item) => (
            <button
              key={item.id}
              disabled={item.id !== "find" && !done}
              className={`nav-item ${view === item.id ? "active" : ""}`}
              onClick={() => navigate(item.id)}
            >
              <item.icon size={18} />
              {item.label}
              {view === item.id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        {run && (
          <button
            className={`audit-nav ${view === "audit" ? "active" : ""}`}
            onClick={() => setView("audit")}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <CheckCircle2 size={16} />
            )}{" "}
            {busy
              ? "Audit in progress"
              : question
                ? "Your input needed"
                : done
                  ? "View audit trail"
                  : "Reconnect audit"}
          </button>
        )}
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <Leaf size={22} />
            <h3>
              Small changes.
              <br />
              Lasting impact.
            </h3>
            <p>A clearer path to a more efficient building.</p>
          </div>
          <button className="help-button" onClick={() => setHelp(true)}>
            <CircleHelp size={17} />
            How it works
            <ArrowRight size={15} />
          </button>
          <div className="profile">
            <span>VS</span>
            <div>
              Vinayak Sinha<small>HackPrinceton workspace</small>
            </div>
            <span className="online-dot" />
          </div>
        </div>
      </aside>
      {mobileNav && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
            >
              <PanelLeftClose size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{title}</strong>
          </div>
          <div className="topbar-right">
            <div className="mode-switch" aria-label="Data mode">
              <button
                className={demo ? "selected" : ""}
                onClick={() => void switchMode(true)}
                disabled={connecting}
              >
                Demo
              </button>
              <button
                className={!demo ? "selected" : ""}
                onClick={() => void switchMode(false)}
                disabled={connecting}
              >
                {connecting ? "Connecting…" : demo ? "Connect API" : "Connected"}
              </button>
            </div>
            <span className="avatar">VS</span>
          </div>
        </header>
        <main>
          <div className={`mode-notice ${demo ? "" : "live"}`}>
            <span className="status-dot" />
            {demo ? "DEMO WORKSPACE" : "CONNECTED WORKSPACE"}
            <span>
              {demo
                ? "Example scenarios and saved results. No live building analysis."
                : "Connected to the team’s building analysis API."}
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
          {view === "find" && (
            <Find
              properties={properties}
              query={query}
              setQuery={setQuery}
              segment={segment}
              setSegment={setSegment}
              loading={searching}
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
                  <h1>
                    Let’s make
                    <br />
                    <em>room for better.</em>
                  </h1>
                  <p className="section-description">
                    Tell us what you want to invest. We’ll find the improvements
                    that fit, and show the assumptions behind every estimate.
                  </p>
                  <div className="setup-property">
                    <HouseViewer office={office} embedded />
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
                    <span className="step-label">01 / 03</span>
                  </div>
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
                      <option value="owner_occupier">Owner-occupier</option>
                      <option value="landlord">Landlord</option>
                      <option value="tenant">Tenant</option>
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
                        Enter January through December, separated by commas.
                      </p>
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
                  <div className="audit-includes">
                    <span>
                      <Check size={15} />
                      Building energy baseline
                    </span>
                    <span>
                      <Check size={15} />
                      Prioritized retrofit plan
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
                    {demo ? "Explore demo audit" : "Start energy audit"}
                    <ArrowRight size={17} />
                  </button>
                  <p className="fineprint">
                    {demo
                      ? "A replay of an illustrative audit, including a sample question."
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
                  <span className="eyebrow">
                    THE BIGGER PICTURE, COMING TOGETHER
                  </span>
                  <h1>
                    {done
                      ? "Clarity looks good on you."
                      : question
                        ? "One detail makes a difference."
                        : "Getting to know your building."}
                  </h1>
                  <p>
                    {run.property.name} · {money(run.request.budget_usd)} cash
                    budget
                  </p>
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
              <div className="audit-grid">
                <section className="audit-timeline">
                  <div className="card-heading">
                    <div>
                      <Sparkles size={17} />
                      <span>{demo ? "Audit replay" : "Agent activity"}</span>
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
                    {events.map((event, i) => (
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
                            {event.stage?.replaceAll("_", " ") ||
                              event.type.replaceAll("_", " ")}
                          </small>
                          <p>{event.message}</p>
                          {event.type === "todo" &&
                            Array.isArray(event.payload.todos) && (
                              <ul className="event-todos">
                                {event.payload.todos.map((raw, i) => {
                                  const task = raw as {
                                    content?: unknown;
                                    status?: unknown;
                                  };
                                  return (
                                    <li key={i}>
                                      <span className="status-dot" />
                                      {String(task.content || "Audit task")}
                                      <small>
                                        {String(
                                          task.status || "pending",
                                        ).replaceAll("_", " ")}
                                      </small>
                                    </li>
                                  );
                                })}
                              </ul>
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
                  {question && (
                    <div className="question-card">
                      <span className="eyebrow">A QUICK QUESTION</span>
                      <h3>{question.prompt}</h3>
                      <p>{question.impact_note}</p>
                      {demo && (
                        <p className="fineprint">
                          Demo replay: your choice advances the saved scenario.
                          Its estimates and original answers remain unchanged.
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
                            {choice.label}
                            <ArrowRight size={14} />
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
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
                </div>
                <button
                  className="secondary-button"
                  onClick={() =>
                    download(
                      `${run.run_id}-report.json`,
                      JSON.stringify(run, null, 2),
                      "application/json",
                    )
                  }
                >
                  <Download size={16} />
                  Export report
                </button>
              </div>
              <div className="result-grid">
                <div className="result-main">
                  {view === "plan" && (
                    <PlanView
                      run={run}
                      onFocus={setFocus}
                      onDocuments={() => setView("documents")}
                    />
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
                        <span>Your investment</span>
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
                          Update plan
                        </button>
                      )}
                      <small>
                        {demo
                          ? budgets.length === 1
                            ? "This shared example has one saved budget. Use a UI sandbox to compare budgets, or connect to live mode."
                            : "Switch between saved budget scenarios."
                          : "Changing your budget reruns the backend analysis."}
                      </small>
                    </form>
                    <p className="budget-rule">
                      <CheckCircle2 size={14} />
                      No-cost measures come first.
                    </p>
                  </section>
                  <section className="insight-card">
                    <Sparkles size={19} />
                    <span className="eyebrow">
                      {demo ? "SAVED EXAMPLE REPORT" : "THE AUDIT’S TAKE"}
                    </span>
                    {demo && (
                      <p className="fineprint">
                        This report retains the original example’s answers.
                        Replay choices do not change the saved analysis.
                      </p>
                    )}
                    <AuditNarrative text={run.narrative_md} warnings={run.warnings} />
                    <button
                      className="text-button"
                      onClick={() => setView("assumptions")}
                    >
                      See the assumptions
                      <ArrowRight size={14} />
                    </button>
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
                          ? "Calibrated to utility history"
                          : "Not calibrated to utility history"}
                      </small>
                    </section>
                  )}
                </aside>
              </div>
              <Warnings warnings={[...run.warnings, ...events.filter((event) => event.type === "fallback" || event.type === "error").map((event) => event.message)]} />
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
                Demo mode uses invented UI fixtures. Live mode connects to your
                team’s API. Sponsor service credentials stay on the backend; the
                browser uses only the domain-scoped Showcase SDK key.
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
