import { useEffect, useRef, useState } from "react";
import { Check, Download, FileText, Info, LoaderCircle } from "lucide-react";
import type {
  DocType,
  DocumentDraft,
  DocumentRequest,
  RunResult,
} from "../lib/types";
import { api, ApiError } from "../lib/api";
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
function demoTypes(commercial: boolean) {
  return Object.keys(labels).filter((key) =>
    commercial
      ? key !== "retrofit_contract_residential"
      : !["retrofit_contract_commercial", "cpace_package"].includes(key),
  ) as DocType[];
}
export function documentScope(run: RunResult, docType: DocType) {
  const measures = [
    ...(run.plan?.selected.map((item) => item.measure) || []),
    ...(docType === "cpace_package"
      ? [
          ...(run.plan?.financeable || []),
          ...run.measures.filter((measure) =>
            measure.finance?.financing.some(
              (scenario) => scenario.kind === "cpace",
            ),
          ),
        ]
      : []),
  ];
  // A selected marginal measure takes precedence over its standalone estimate.
  return measures.filter(
    (measure, index) =>
      measures.findIndex((item) => item.measure_id === measure.measure_id) ===
      index,
  );
}
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
  const [available, setAvailable] = useState<DocType[]>(() =>
    demo ? demoTypes(commercial) : [],
  );
  const [loadingTemplates, setLoadingTemplates] = useState(!demo);
  const [templateNotice, setTemplateNotice] = useState("");
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
  useEffect(() => {
    setApproved(false);
    setDraft(null);
    setTemplateNotice("");
    const abort = new AbortController();
    if (demo) {
      setAvailable(demoTypes(commercial));
      setLoadingTemplates(false);
      return;
    }
    setAvailable([]);
    setLoadingTemplates(true);
    void api
      .templates(state, run.property.segment, abort.signal)
      .then((types) => {
        if (abort.signal.aborted) return;
        const known = types.filter((type) => type in labels);
        setAvailable(known);
        setDocType((current) =>
          known.includes(current) ? current : known[0] || current,
        );
        if (!known.length)
          setTemplateNotice(
            "No document template is available for this property type and jurisdiction yet.",
          );
      })
      .catch((error) => {
        if (!abort.signal.aborted)
          setTemplateNotice(
            error instanceof Error
              ? `Could not load available templates: ${error.message}`
              : "Could not load available templates.",
          );
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoadingTemplates(false);
      });
    return () => abort.abort();
  }, [demo, state, run.property.segment]);
  function invalidate() {
    version.current++;
    setDraft(null);
    setApproved(false);
    setBusy(false);
  }
  const planIds = new Set(
    run.plan?.selected.map((item) => item.measure.measure_id),
  );
  const scope = documentScope(run, docType);
  const selectedScope = selected.filter((id) =>
    scope.some((measure) => measure.measure_id === id),
  );
  async function generate(event: React.FormEvent) {
    event.preventDefault();
    if (!approved || !selectedScope.length || !available.includes(docType))
      return;
    setBusy(true);
    setError("");
    const current = ++version.current;
    const body: DocumentRequest = {
      run_id: run.run_id,
      doc_type: docType,
      state,
      measure_ids: selectedScope,
      fields: { owner_name: owner, contractor_name: contractor },
    };
    try {
      const result = demo ? demoDraft(body) : await api.draft(body);
      if (current === version.current) setDraft(result);
    } catch (e) {
      if (
        current === version.current &&
        e instanceof ApiError &&
        e.code === "template_not_available"
      ) {
        const remaining = available.filter((type) => type !== docType);
        setAvailable(remaining);
        if (remaining[0]) setDocType(remaining[0]);
        setTemplateNotice(
          "That template is no longer available for this jurisdiction. Choose another available document.",
        );
        setApproved(false);
      } else if (current === version.current)
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
        {loadingTemplates && (
          <p role="status">Checking available document templates…</p>
        )}
        {templateNotice && (
          <p className="inline-note" role="status">
            {templateNotice}
          </p>
        )}
        <div className="form-grid">
          <label>
            Document type
            <select
              value={docType}
              disabled={loadingTemplates || !available.length}
              onChange={(e) => {
                setDocType(e.target.value as DocType);
                setSelected(
                  run.plan?.selected.map((item) => item.measure.measure_id) ||
                    [],
                );
                invalidate();
              }}
            >
              {Object.entries(labels)
                .filter(([key]) => available.includes(key as DocType))
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
          {docType === "cpace_package" && (
            <p className="inline-note">
              This package is a financing review. Template availability does not
              establish eligibility; programme, savings-to-investment tests and
              owner consent still need confirmation.
            </p>
          )}
          {scope.map((measure) => (
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
              {!planIds.has(measure.measure_id) && (
                <small>Outside the selected plan · financing review only</small>
              )}
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
            !selectedScope.length ||
            busy ||
            !owner.trim() ||
            !contractor.trim() ||
            loadingTemplates ||
            !available.includes(docType)
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
            {!draft.statutory_checks.length && (
              <p className="inline-note">
                No statutory checks were supplied for this draft. Its legal
                requirements have not been checked.
              </p>
            )}
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
                  {check.requirement_id && (
                    <strong>{check.requirement_id} · </strong>
                  )}
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
