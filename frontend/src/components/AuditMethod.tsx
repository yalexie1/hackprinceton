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
      How would you like to build your plan?
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as AuditMethod)}
        aria-describedby="audit-method-detail"
      >
        <option value="server">Use the saved property audit</option>
        <option value="analysis">Calculate a new plan</option>
      </select>
      <small id="audit-method-detail">
        {value === "analysis"
          ? "Use the building records, your budget and any utility bills you add to calculate a plan. The property’s records must be available."
          : "Open the property’s saved audit. If your budget has changed, the service checks the plan again. Example results are never used."}
      </small>
    </label>
  );
}
