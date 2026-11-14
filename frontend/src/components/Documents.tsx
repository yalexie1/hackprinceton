import { useEffect, useRef, useState } from "react";
import { Check, Download, FileText, Info, LoaderCircle } from "lucide-react";
import type {
  DocType,
  DocumentDraft,
  DocumentRequest,
  RunResult,
} from "../lib/types";
import { api } from "../lib/api";
import { demoDraft } from "../lib/fixtures";
import { download } from "../lib/format";
const labels: Record<DocType, string> = {
  retrofit_contract_residential: "Residential retrofit contract",
  retrofit_contract_commercial: "Commercial retrofit contract",
  solar_installation_agreement: "Solar installation agreement",
  bid_package_rfp: "Contractor bid package",
  energy_savings_guarantee: "Energy savings guarantee",
  cpace_package: "Commercial C-PACE package",
};
function DraftText({ text }: { text: string }) {
  return (
    <div className="draft-text">
      {text.split("\n").map((line, i) => {
        const content = line
          .split(/(\{\{[^}]+\}\})/g)
          .map((chunk, j) =>
            chunk.startsWith("{{") ? <mark key={j}>{chunk}</mark> : chunk,
          );
        return line.startsWith("# ") ? (
          <h2 key={i}>{line.slice(2)}</h2>
        ) : line.startsWith("## ") ? (
          <h3 key={i}>{line.slice(3)}</h3>
        ) : (
          <p key={i}>{content.length && line ? content : "\u00a0"}</p>
        );
      })}
    </div>
  );
}
export default function Documents({
  run,
  demo,
}: {
  run: RunResult;
  demo: boolean;
}) {
  const commercial = run.property.segment === "commercial";
  const [docType, setDocType] = useState<DocType>(
    commercial
      ? "retrofit_contract_commercial"
      : "retrofit_contract_residential",
  );
  const [state, setState] = useState<"CA" | "TX">(run.property.state || "CA");
  const [owner, setOwner] = useState("");
  const [contractor, setContractor] = useState("");
  const [selected, setSelected] = useState(
    run.plan?.selected.map((i) => i.measure.measure_id) || [],
  );
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<DocumentDraft | null>(null);
  const [error, setError] = useState("");
  const version = useRef(0);
  useEffect(() => {
    version.current++;
    setDraft(null);
    setApproved(false);
    setBusy(false);
    return () => {
      version.current++;
    };
  }, [run]);
  function invalidate() {
    version.current++;
    setDraft(null);
    setApproved(false);
    setBusy(false);
  }
  async function generate(event: React.FormEvent) {
    event.preventDefault();
    if (!approved || !selected.length) return;
    setBusy(true);
    setError("");
    const current = ++version.current;
    const body: DocumentRequest = {
      run_id: run.run_id,
      doc_type: docType,
      state,
      measure_ids: selected,
      fields: { owner_name: owner, contractor_name: contractor },
    };
    try {
      const result = demo ? demoDraft(body) : await api.draft(body);
      if (current === version.current) setDraft(result);
    } catch (e) {
      if (current === version.current)
        setError(e instanceof Error ? e.message : "Drafting failed.");
    } finally {
      if (current === version.current) setBusy(false);
    }
  }
  return (
    <section className="documents-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">FROM PLAN TO PROJECT</span>
          <h2>Put the next step in writing.</h2>
        </div>
        <FileText size={26} />
      </div>
      <p className="section-description">
        Confirm the parties and scope, then review the draft and any unfilled
        terms.
      </p>
      <form onSubmit={generate}>
        <div className="form-grid">
          <label>
            Document type
            <select
              value={docType}
              onChange={(e) => {
                setDocType(e.target.value as DocType);
                invalidate();
              }}
            >
              {Object.entries(labels)
                .filter(([key]) =>
                  commercial
                    ? key !== "retrofit_contract_residential"
                    : ![
                        "retrofit_contract_commercial",
                        "cpace_package",
                      ].includes(key),
                )
                .map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Property jurisdiction
            <select
              value={state}
              onChange={(e) => {
                setState(e.target.value as "CA" | "TX");
                invalidate();
              }}
            >
              <option value="CA">California</option>
              <option value="TX">Texas</option>
            </select>
          </label>
          <label>
            Owner’s legal name
            <input
              required
              value={owner}
              onChange={(e) => {
                setOwner(e.target.value);
                invalidate();
              }}
              placeholder="Enter the owner’s name"
            />
          </label>
          <label>
            Contractor’s legal name
            <input
              required
              value={contractor}
              onChange={(e) => {
                setContractor(e.target.value);
                invalidate();
              }}
              placeholder="Enter the contractor’s name"
            />
          </label>
        </div>
        <fieldset className="measure-checks">
          <legend>Scope of work</legend>
          {run.plan?.selected.map(({ measure }) => (
            <label key={measure.measure_id}>
              <input
                type="checkbox"
                checked={selected.includes(measure.measure_id)}
                onChange={(e) => {
                  setSelected(
                    e.target.checked
                      ? [...selected, measure.measure_id]
                      : selected.filter((id) => id !== measure.measure_id),
                  );
                  invalidate();
                }}
              />
              {measure.title}
            </label>
          ))}
        </fieldset>
        <label className="approval">
          <input
            type="checkbox"
            checked={approved}
            onChange={(e) => setApproved(e.target.checked)}
          />
          I have reviewed the parties and selected measures and approve creating
          this draft.
        </label>
        <button
          className="primary-button"
          disabled={
            !approved ||
            !selected.length ||
            busy ||
            !owner.trim() ||
            !contractor.trim()
          }
        >
          {busy ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <FileText size={16} />
          )}{" "}
          {busy ? "Preparing draft…" : "Prepare draft"}
        </button>
      </form>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {draft && (
        <section className="document-preview">
          <div className="card-heading">
            <div>
              <FileText size={16} />
              <span>Review your draft</span>
            </div>
            <button
              className="text-button"
              onClick={() =>
                download(
                  `${draft.doc_type}-${draft.state}.md`,
                  `${draft.disclaimer}\n\n${draft.markdown}`,
                )
              }
            >
              <Download size={15} />
              Export Markdown
            </button>
          </div>
          <p className="inline-note">
            <Info size={16} />
            {draft.disclaimer}
          </p>
          <DraftText text={draft.markdown} />
          <div className="document-checklist">
            <h3>Review checklist</h3>
            {draft.unfilled_placeholders.length > 0 && (
              <p className="fineprint">
                Unfilled terms:{" "}
                {draft.unfilled_placeholders
                  .map((p) => p.replaceAll("_", " "))
                  .join(", ")}
                .
              </p>
            )}
            {draft.statutory_checks.map((check, i) => (
              <div
                key={i}
                className={check.satisfied ? "check-pass" : "check-pending"}
              >
                {check.satisfied ? <Check size={16} /> : <Info size={16} />}
                <span>
                  {check.requirement}
                  <small>
                    {check.citation}
                    {check.note && ` · ${check.note}`}
                  </small>
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </section>
  );
}
