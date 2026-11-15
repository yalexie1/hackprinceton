import { rankedZips, type RoiRow } from "../lib/roi-map";

export const usd = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;

export default function RoiTable({ rows, limit = 15 }: { rows: RoiRow[]; limit?: number }) {
  const ranked = rankedZips(rows).slice(0, limit);
  return (
    <table className="roi-table">
      <caption>Quickest estimated payback first</caption>
      <thead>
        <tr>
          <th>Zip</th>
          <th>Payback</th>
          <th>Saves per year</th>
          <th>Cost (no incentives)</th>
        </tr>
      </thead>
      <tbody>
        {ranked.map((r) => (
          <tr key={r.zip}>
            <td>{r.zip}</td>
            <td>{r.payback_years} years</td>
            <td>{usd(r.annual_savings_usd)}</td>
            <td>{usd(r.net_upfront_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
