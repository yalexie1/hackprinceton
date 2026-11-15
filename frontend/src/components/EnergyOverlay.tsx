import { useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { ArrowDownRight, Leaf, X, Zap } from "lucide-react";
import { energyUpgrades } from "../lib/energy-explorer";
import type {
  EnergyPart,
  EnergyPoint,
  EnergyUpgrade,
} from "../lib/energy-explorer";
import type { HouseController, HouseMode } from "../lib/house-scene";
import type { RunResult } from "../lib/types";
import { money, number } from "../lib/format";

const partNames: Record<EnergyPart, string> = {
  solar: "Solar",
  roof: "Cool roof",
  attic: "Insulation",
  envelope: "Air sealing & walls",
  windows: "Windows",
  lighting: "LED lighting",
  hvac: "Heating & cooling",
  water: "Hot water",
  controls: "Thermostat",
  workspace: "Workspace",
};

export function UpgradeDetails({
  upgrade,
  onClose,
}: {
  upgrade: EnergyUpgrade;
  onClose: () => void;
}) {
  const { measure, status, reason } = upgrade;
  const finance = measure.finance;
  const savings = measure.savings;
  return (
    <section
      className={`energy-tooltip ${status}`}
      aria-label="Upgrade details"
      aria-live="polite"
    >
      <div className="energy-tooltip-top">
        <span>
          {status === "planned"
            ? "IN YOUR PLAN"
            : status === "opportunity"
              ? "ADDITIONAL OPTION"
              : "NOT INCLUDED"}
        </span>
        <button aria-label="Close upgrade details" onClick={onClose}>
          <X size={15} />
        </button>
      </div>
      <h3>{measure.title}</h3>
      <p>{measure.description}</p>
      {status !== "unavailable" && (
        <div className="energy-tooltip-grid">
          <div>
            <span>Estimated annual savings</span>
            <strong>
              {finance
                ? money(finance.annual_savings_usd.expected)
                : "Savings not estimated"}
              {finance && <small>/ yr</small>}
            </strong>
          </div>
          <div>
            <span>Upfront cost</span>
            <strong>
              {finance
                ? money(finance.net_upfront_usd.expected)
                : "Quote needed"}
            </strong>
          </div>
          {savings && (
            <div>
              <span>Electricity saved</span>
              <strong>
                {number(savings.electricity_kwh.expected)}
                <small> kWh / yr</small>
              </strong>
            </div>
          )}
          {savings && (
            <div>
              <span>CO₂ avoided</span>
              <strong>
                {number(savings.co2_kg.expected)}
                <small> kg / yr</small>
              </strong>
            </div>
          )}
          {savings && savings.gas_kwh.expected !== 0 && (
            <div>
              <span>Gas saved</span>
              <strong>
                {number(savings.gas_kwh.expected)}
                <small> kWh thermal / yr</small>
              </strong>
            </div>
          )}
          {finance?.simple_payback_years && (
            <div>
              <span>Simple payback</span>
              <strong>
                {number(finance.simple_payback_years.expected, 1)}
                <small> years</small>
              </strong>
            </div>
          )}
        </div>
      )}
      {measure.solar && (
        <div className="energy-design-note">
          {number(measure.solar.system_kw_dc, 2)} kW solar design ·{" "}
          {measure.solar.panel_count} panels ·{" "}
          {number(measure.solar.annual_kwh.expected)} kWh / yr generated
        </div>
      )}
      {reason && <p className="energy-caveat">{reason}</p>}
      {measure.flags.map((flag) => (
        <p className="energy-caveat" key={flag.key}>
          {flag.message}
        </p>
      ))}
      {measure.warnings.slice(0, 2).map((warning, i) => (
        <p className="energy-caveat" key={i}>
          {warning}
        </p>
      ))}
      <footer>
        {status === "planned"
          ? "Savings reflect this upgrade’s place in the plan."
          : "Evaluated separately. Its savings are not added to your plan’s totals."}{" "}
        Location shown on an illustrative model.
      </footer>
    </section>
  );
}

export default function EnergyOverlay({
  run,
  controller,
  mode,
  hoverRef,
  projectRef,
}: {
  run: RunResult;
  controller: HouseController | null;
  mode: HouseMode;
  hoverRef: MutableRefObject<((part: EnergyPart | null) => void) | null>;
  projectRef: MutableRefObject<((points: EnergyPoint[]) => void) | null>;
}) {
  const upgrades = useMemo(() => energyUpgrades(run), [run]);
  const [all, setAll] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [pinned, setPinned] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const markers = useRef(new Map<EnergyPart, HTMLButtonElement>());
  const visible = useMemo(
    () => upgrades.filter((u) => all || u.status === "planned"),
    [upgrades, all],
  );
  const parts = [...new Set(visible.map((u) => u.part))];
  const active = visible.find((u) => u.measure.measure_id === activeId);
  const planned = upgrades.filter((u) => u.status === "planned");
  function cancelHide() {
    if (hideTimer.current) clearTimeout(hideTimer.current);
  }
  function inspect(id: string) {
    cancelHide();
    setActiveId(id);
  }
  function scheduleHide() {
    cancelHide();
    if (!pinned) hideTimer.current = setTimeout(() => setActiveId(null), 180);
  }
  function close() {
    cancelHide();
    setActiveId(null);
    setPinned(false);
  }
  useEffect(() => {
    hoverRef.current = (part) => {
      const next = visible.find((u) => u.part === part);
      if (next) {
        if (pinned && next.measure.measure_id !== activeId) setPinned(false);
        inspect(next.measure.measure_id);
      } else if (!pinned) scheduleHide();
    };
    projectRef.current = (points) => {
      for (const point of points) {
        const marker = markers.current.get(point.part);
        if (marker) {
          marker.style.transform = `translate(${point.x}px, ${point.y}px) translate(-50%, -50%)`;
          marker.hidden = !point.visible;
        }
      }
    };
    return () => {
      hoverRef.current = null;
      projectRef.current = null;
      cancelHide();
    };
  }, [visible, pinned, activeId]);
  useEffect(() => {
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", dismiss);
    return () => window.removeEventListener("keydown", dismiss);
  }, []);
  useEffect(() => {
    controller?.setEnergy(
      parts,
      planned.map((u) => u.part),
      active?.part || null,
    );
  }, [controller, visible, activeId]);
  useEffect(() => {
    close();
  }, [run.run_id, mode]);
  useEffect(() => () => controller?.setEnergy([], [], null), [controller]);
  return (
    <div
      className="energy-overlay"
      onKeyDown={(event) => {
        if (event.key === "Escape") close();
      }}
    >
      <div className="energy-plan-summary">
        <span className="scene-label">
          {run.run_id.startsWith("demo") ||
          run.warnings.some((w) => /illustrative/i.test(w))
            ? "EXAMPLE ENERGY PLAN"
            : "YOUR PROPOSED ENERGY PLAN"}
        </span>
        <strong>
          <ArrowDownRight size={20} />
          {money(run.plan!.total_annual_savings_usd.expected)}
          <small>/ year</small>
        </strong>
        <span>
          {planned.length} planned upgrades ·{" "}
          {number(run.plan!.total_co2_kg.expected)} kg CO₂ avoided / yr
        </span>
        <small>
          {run.property.name} · {money(run.request.budget_usd)} budget
        </small>
      </div>
      <div className="energy-legend">
        <div className="energy-scope" role="group" aria-label="Energy findings">
          <button
            aria-pressed={!all}
            onClick={() => {
              setAll(false);
              close();
            }}
          >
            Your plan <span>{planned.length}</span>
          </button>
          <button
            aria-pressed={all}
            onClick={() => {
              setAll(true);
              close();
            }}
          >
            All findings <span>{upgrades.length}</span>
          </button>
        </div>
        <span className="energy-hover-hint">
          <Zap size={11} /> Hover a highlight, or tap to inspect
        </span>
        <div
          className="energy-findings"
          role="group"
          aria-label="Inspect energy upgrades"
        >
          {visible.map((upgrade, index) => (
            <button
              key={upgrade.measure.measure_id}
              className={upgrade.status}
              aria-pressed={activeId === upgrade.measure.measure_id}
              onMouseEnter={() => inspect(upgrade.measure.measure_id)}
              onMouseLeave={scheduleHide}
              onFocus={() => inspect(upgrade.measure.measure_id)}
              onBlur={scheduleHide}
              onClick={() => {
                inspect(upgrade.measure.measure_id);
                setPinned(true);
              }}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              {upgrade.measure.title}
              <i />
              {upgrade.status === "planned" && upgrade.measure.finance && (
                <small>
                  {money(upgrade.measure.finance.annual_savings_usd.expected)}
                  /yr
                </small>
              )}
            </button>
          ))}
        </div>
      </div>
      <div className="energy-hotspots">
        {parts.map((part) => {
          const upgrade = visible.find((u) => u.part === part)!;
          return (
            <button
              key={part}
              ref={(node) => {
                if (node) markers.current.set(part, node);
                else markers.current.delete(part);
              }}
              hidden
              className={`energy-hotspot ${upgrade.status} ${active?.part === part ? "active" : ""}`}
              aria-label={`Inspect ${partNames[part]}`}
              aria-expanded={active?.part === part}
              onMouseEnter={() => inspect(upgrade.measure.measure_id)}
              onMouseLeave={scheduleHide}
              onFocus={() => inspect(upgrade.measure.measure_id)}
              onBlur={scheduleHide}
              onClick={() => {
                inspect(upgrade.measure.measure_id);
                setPinned(true);
              }}
            >
              <span>
                <Zap size={12} />
              </span>
              <small>{partNames[part]}</small>
            </button>
          );
        })}
      </div>
      {active ? (
        <div
          className="energy-detail-host"
          onMouseEnter={cancelHide}
          onMouseLeave={scheduleHide}
        >
          <UpgradeDetails upgrade={active} onClose={close} />
          {visible.filter((u) => u.part === active.part).length > 1 && (
            <div className="energy-related">
              {visible
                .filter((u) => u.part === active.part)
                .map((u) => (
                  <button
                    key={u.measure.measure_id}
                    aria-pressed={u.measure.measure_id === activeId}
                    onClick={() => {
                      inspect(u.measure.measure_id);
                      setPinned(true);
                    }}
                  >
                    {u.measure.title}
                  </button>
                ))}
            </div>
          )}
        </div>
      ) : (
        <div className="energy-idle-card">
          <Leaf size={21} />
          <div>
            <small>THE IMPROVEMENTS, EXPLAINED</small>
            <strong>Inspect an improvement.</strong>
            <p>
              Hover the solar panels or lighting to see what changes — and what
              it could save.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
