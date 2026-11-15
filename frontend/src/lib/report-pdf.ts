import { jsPDF } from "jspdf";
import type { Ranged, RunResult } from "./types";
import { money, number } from "./format";
import { assumptionDisplay, evidenceText, inputName, readableText, warningText } from "./homeowner-language";
import { hasPlaceholderEvidence } from "./real-audit";

// Built entirely in the browser; no audit or imagery is sent to a report service.
export function createAuditPdf(run: RunResult): jsPDF {
  const pdf = new jsPDF({ unit: "mm", format: "a4" });
  const left = 18, width = 174, bottom = 273;
  let y = 20;
  const plain = (s: string) => s.normalize("NFKD").replace(/[–—−]/g,"-").replace(/[‘’]/g,"'").replace(/[“”]/g,'"').replace(/²/g,"2").replace(/[^\x20-\x7E\n]/g, "");
  const ensure = (height: number) => { if (y + height > bottom) { pdf.addPage(); y = 22; } };
  function text(value: string, size = 11, bold = false, color: [number,number,number] = [36,55,48]) {
    pdf.setFont("helvetica", bold ? "bold" : "normal"); pdf.setFontSize(size); pdf.setTextColor(...color);
    const lines = pdf.splitTextToSize(plain(value), width) as string[];
    const lineHeight = size * 0.49;
    for (const line of lines) { ensure(lineHeight); pdf.text(line, left, y); y += lineHeight; }
    y += 3;
  }
  function heading(title: string) { ensure(24); y += 4; text(title,16,true,[24,78,57]); }
  const range = (r: Ranged, currency = true) => `${currency ? money(r.expected) : number(r.expected,2)} (estimated range ${currency ? money(r.low) : number(r.low,2)} to ${currency ? money(r.high) : number(r.high,2)})`;
  text("LETO  /  HOME ENERGY PLAN",11,true,[24,78,57]);
  text(run.property.name,24,true);
  text([run.property.address,run.property.city,run.property.state].filter(Boolean).join(", "));
  text(`Report exported ${new Date().toLocaleDateString("en-US")}. This is the saved audit's original calculation.`,10);
  text("Use this plan to prepare for quotes and on-site checks. Savings are estimates, not guarantees. Model ranges may miss important uncertainty; they have not been validated for this individual property.",11);
  heading("Your plan at a glance");
  if (run.plan) {
    text(`Estimated annual bill savings: ${range(run.plan.total_annual_savings_usd)}`,12,true);
    text(`Cash needed upfront: ${range(run.plan.total_upfront_usd)}`);
    text(`Your cash budget: ${money(run.plan.budget_usd)}`);
    text(`Estimated annual emissions reduction: ${range(run.plan.total_co2_kg,false)} kilograms of carbon dioxide.`);
    if (run.plan.total_annual_savings_usd.low < 0) text("The lower savings estimate is negative: energy costs could increase under that scenario. Confirm the assumptions before deciding.");
  } else text("A completed plan is not available in this audit.");
  heading("Current energy use");
  if (run.baseline) {
    text(`Estimated annual electricity use: ${range(run.baseline.annual.electricity_kwh,false)} kWh.`);
    text(`Estimated annual gas energy: ${range(run.baseline.annual.gas_kwh,false)} kWh.`);
    text(`Estimated annual energy bill: ${range(run.baseline.annual.cost_usd)}.`);
    text(run.baseline.calibrated_to_bills ? "This audit reports that its baseline was adjusted using utility bills. This does not guarantee future savings." : "This estimate was not matched to the property's utility bills.");
  } else text("Current energy use was not available.");
  heading("Included improvements");
  for (const item of run.plan?.selected || []) {
    ensure(34); text(`${item.rank}. ${readableText(item.measure.title)}`,13,true);
    const m = item.measure; text(readableText(m.description));
    if (m.finance) {
      text(`Upfront cost: ${range(m.finance.net_upfront_usd)}. Annual savings: ${range(m.finance.annual_savings_usd)}.`);
      text(`Cost source: ${readableText(m.finance.cost_source || "No source recorded.")}`,10);
    }
    for (const warning of [...m.warnings,...m.flags.map(f => f.message)]) text(warningText(warning),10);
  }
  if (!run.plan?.selected.length) text("No improvements are included in the current plan.");
  if (run.plan?.financeable.length) {
    heading("Options needing more budget");
    text("These options are outside the selected plan. Their savings are not included in your plan totals. Financing needs separate eligibility checks.");
    for (const m of run.plan.financeable) { text(readableText(m.title),12,true); if (m.finance) text(`Upfront cost: ${range(m.finance.net_upfront_usd)}. Annual savings: ${range(m.finance.annual_savings_usd)}.`); }
  }
  if (run.plan?.skipped.length) {
    heading("Other findings");
    for (const item of run.plan.skipped) text(`${readableText(item.measure_id)}: ${readableText(item.detail)}`);
  }
  heading("What to check before deciding");
  for (const warning of [...new Set(run.warnings)]) text(warningText(warning));
  text("Confirm roof dimensions and condition, electrical capacity, hidden insulation, actual utility prices and installation costs with the appropriate professional. Obtain firm quotes before committing.");
  heading("Building details and their sources");
  for (const a of run.building_model?.assumptions || []) {
    ensure(26);
    const value = hasPlaceholderEvidence(a) ? "Needs confirmation - no verified value" : `${assumptionDisplay(a).value} (${assumptionDisplay(a).range})`;
    text(`${inputName(a.key,a.label)}: ${value}`,11,true);
    for (const e of a.evidence) text(hasPlaceholderEvidence({evidence:[e]}) ? "A property measurement or confirmed record is needed." : evidenceText(e),10);
  }
  const pages = pdf.getNumberOfPages();
  for (let page=1;page<=pages;page++) { pdf.setPage(page); pdf.setDrawColor(205,218,209); pdf.line(left,281,192,281); pdf.setFont("helvetica","normal"); pdf.setFontSize(9); pdf.setTextColor(80,98,88); pdf.text("LETO | Estimates for review before installation",left,287); pdf.text(`${page} / ${pages}`,192,287,{align:"right"}); }
  return pdf;
}
export async function exportAuditPdf(run: RunResult) {
  const name = run.property.name.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
  createAuditPdf(run).save(`${name || "property"}-energy-plan.pdf`);
}
