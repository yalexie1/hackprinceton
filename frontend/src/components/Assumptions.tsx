import { useState } from "react";
import { Info, Pencil, RotateCcw } from "lucide-react";
import type { Assumption, RunResult } from "../lib/types";
import { assumptionDisplay, evidenceText, isPercentageInput, friendlyUnit, inputName, readableText } from "../lib/homeowner-language";
import { hasPlaceholderEvidence } from "../lib/real-audit";
/**
 * A readable name for an assumption.
 *
 * The backend sets a friendly label for almost every input ("Ceiling height", "People working
 * in the suite"), but a user override arrives with its own machine key as the label, so the page
 * showed `lighting.lamp_type`. A key is recognisable by having dots and no spaces; anything that
 * already reads as a sentence is left exactly as it is.
 */
export function readableLabel(label: string, key: string): string {
  return inputName(key, hasPlaceholderEvidence({ label }) ? "" : label);
}

const sourceNames: Record<string, string> = {
  vintage_default: "Estimate based on building age",
  published_default: "Published reference value",
  measured: "Measured input",
  user: "Provided during the audit",
  vision: "Estimated from images",
  costar: "CoStar property records",
  vexcel: "Vexcel aerial imagery",
  matterport: "Matterport building scan",
  calibrated: "Matched to utility bills",
};
export default function Assumptions({
  run,
  demo,
  busy,
  onSave,
}: {
  run: RunResult;
  demo: boolean;
  busy: boolean;
  onSave: (key: string, value: number | string | boolean) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const assumptions = run.building_model?.assumptions || [];
  function begin(a: Assumption) {
    setEditing(a.key);
    setValue(
      hasPlaceholderEvidence(a)
        ? ""
        : typeof a.value === "object"
          ? String(a.value.expected * (isPercentageInput(a.key) ? 100 : 1))
          : String(a.value),
    );
  }
  return (
    <section>
      <div className="section-heading">
        <div>
          <span className="eyebrow">THE INPUTS BEHIND YOUR PLAN</span>
          <h2>What we know about your building.</h2>
        </div>
        <Info size={25} />
      </div>
      <p className="section-description">
        See what was measured and what was estimated. Correct an editable detail
        to update your plan.
      </p>
      <details className="financial-guide">
        <summary>How to read these inputs</summary>
        <p>
          Each source label explains where a detail came from. Measured details
          come from the scan. Estimates use images, building age or reference
          values and may need checking on site.
        </p>
        <p>
          Efficiency ratings describe how much useful heating or cooling equipment delivers. Higher ratings usually mean less energy is needed. Heat-transfer ratings describe how easily heat escapes through a wall, roof or window; lower values mean better insulation. Temperatures are in degrees Celsius and areas are in square metres.
        </p>
      </details>
      {demo && (
        <p className="inline-note">
          <Info size={15} />
          These are saved example assumptions. Editing is available when
          connected to a live audit.
        </p>
      )}
      <div className="assumption-list">
        {assumptions.map((a) => (
          <article className="assumption" key={a.key}>
            <div className="assumption-top">
              <div>
                <span className="source-badge">
                  {sourceNames[a.source] || a.source.replaceAll("_", " ")}
                </span>
                <h3>{readableLabel(a.label, a.key)}</h3>
              </div>
              {a.user_editable && (
                <button
                  className="icon-button"
                  disabled={demo || !a.user_editable || busy}
                  aria-label={`Edit ${readableLabel(a.label, a.key)}`}
                  title={
                    demo
                      ? "Connect to live mode to edit assumptions"
                      : "Edit assumption"
                  }
                  onClick={() => begin(a)}
                >
                  <Pencil size={16} />
                </button>
              )}
            </div>
            <div className="assumption-body">
              <div>
                <strong>
                  {hasPlaceholderEvidence(a)
                    ? "Needs confirmation"
                    : assumptionDisplay(a).value}
                </strong>
                <small>
                  {hasPlaceholderEvidence(a)
                    ? "No verified value is available for this detail."
                    : assumptionDisplay(a).range}
                </small>
              </div>
              <div className="confidence">
                <span>
                  {hasPlaceholderEvidence(a)
                    ? "Check this detail"
                    : a.source === "measured"
                      ? "Measured in the scan"
                      : "Review the source below"}
                </span>
              </div>
            </div>
            <details className="assumption-evidence">
              <summary>Where this detail came from</summary>
              {a.evidence.map((e, i) => (
                <p className="fineprint" key={i}>
                  {hasPlaceholderEvidence({ evidence: [e] })
                    ? "This detail needs a property measurement or a confirmed record."
                    : evidenceText(e)}
                </p>
              ))}
            </details>
            {editing === a.key && (
              <form
                className="edit-assumption"
                onSubmit={(event) => {
                  event.preventDefault();
                  const next =
                    typeof a.value === "object"
                      ? Number(value) / (isPercentageInput(a.key) ? 100 : 1)
                      : typeof a.value === "boolean"
                        ? value === "true"
                        : value;
                  if (typeof next === "number" && !Number.isFinite(next))
                    return;
                  onSave(a.key, next);
                  setEditing(null);
                }}
              >
                <label>
                  New {readableLabel(a.label, a.key).toLowerCase()}
                  {typeof a.value === "object" && ` (${isPercentageInput(a.key) ? "%" : friendlyUnit(a.value.unit) || "ratio"})`}
                  {typeof a.value === "boolean" ? (
                    <select
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                    >
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  ) : (
                    <input
                      required
                      type={typeof a.value === "object" ? "number" : "text"}
                      step="any"
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                    />
                  )}
                </label>
                <button className="primary-button" disabled={busy}>
                  <RotateCcw size={15} />
                  Update &amp; rerun
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setEditing(null)}
                >
                  Cancel
                </button>
              </form>
            )}
          </article>
        ))}
      </div>
      {!assumptions.length && (
        <div className="empty-state">
          <Info />
          <p>The audit has not published its assumptions yet.</p>
        </div>
      )}
    </section>
  );
}
