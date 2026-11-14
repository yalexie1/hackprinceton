export type AuditMethod = "server" | "analysis";

export default function AuditMethodChoice({
  value,
  onChange,
}: {
  value: AuditMethod;
  onChange: (value: AuditMethod) => void;
}) {
  return (
    <label>
      Audit method
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as AuditMethod)}
        aria-describedby="audit-method-detail"
      >
        <option value="server">Server default</option>
        <option value="analysis">Real analysis (about 10 s)</option>
      </select>
      <small id="audit-method-detail">
        {value === "analysis"
          ? "Compute a plan from live property data using your budget, role and utility history. Requires the server’s live-data connection. Timing varies by property."
          : "Use the server’s configured audit mode: a recorded demo or an agent run. Each result shows its data source and delivery mode."}
      </small>
    </label>
  );
}
