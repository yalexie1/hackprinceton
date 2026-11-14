import { useState } from "react";
import { Info, Pencil, RotateCcw } from "lucide-react";
import type { Assumption, RunResult } from "../lib/types";
import { number, ranged } from "../lib/format";
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
      typeof a.value === "object" ? String(a.value.expected) : String(a.value),
    );
  }
  return (
    <section>
      <div className="section-heading">
        <div>
          <span className="eyebrow">KNOW WHAT’S BEHIND THE NUMBERS</span>
          <h2>Good decisions start with clarity.</h2>
        </div>
        <Info size={25} />
      </div>
      <p className="section-description">
        Measured, inferred, and user-provided inputs stay visible. Updating an
        assumption asks the backend to run the analysis again.
      </p>
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
                  {a.source.replaceAll("_", " ")}
                </span>
                <h3>{a.label}</h3>
              </div>
              <button
                className="icon-button"
                disabled={demo || !a.user_editable || busy}
                aria-label={`Edit ${a.label}`}
                title={
                  demo
                    ? "Connect to live mode to edit assumptions"
                    : "Edit assumption"
                }
                onClick={() => begin(a)}
              >
                <Pencil size={16} />
              </button>
            </div>
            <div className="assumption-body">
              <div>
                <strong>
                  {typeof a.value === "object"
                    ? `${number(a.value.expected, 2)} ${a.value.unit}`
                    : String(a.value)}
                </strong>
                <small>
                  {typeof a.value === "object"
                    ? ranged(a.value)
                    : "Categorical assumption"}
                </small>
              </div>
              <div className="confidence">
                <span>Confidence {number(a.confidence * 100)}%</span>
                <progress value={a.confidence} max="1" />
              </div>
            </div>
            {a.evidence.map((e, i) => (
              <p className="fineprint" key={i}>
                {e.kind.replaceAll("_", " ")}: {e.ref}
                {e.note && ` · ${e.note}`}
              </p>
            ))}
            {editing === a.key && (
              <form
                className="edit-assumption"
                onSubmit={(event) => {
                  event.preventDefault();
                  const next =
                    typeof a.value === "object"
                      ? Number(value)
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
                  New {a.label.toLowerCase()}
                  {typeof a.value === "boolean" ? (
                    <select
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                    >
                      <option value="true">True</option>
                      <option value="false">False</option>
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
