import { BookOpen, Database, Workflow } from "lucide-react";
const steps = [
  ["Get to know your property", "We bring together the property record, interior scan and aerial survey. Your audit identifies missing information and explains when an estimate is used instead."],
  ["Separate facts from estimates", "Room measurements help describe the building. Photographs can suggest the type of windows, lighting and equipment, but a photograph cannot confirm hidden insulation or equipment performance. The Assumptions page explains the source of each input and lets you correct editable details."],
  ["Estimate current energy use", "We calculate heating, cooling, hot water, lighting and appliance use over a year of weather. This is an estimate of your building, not a meter reading. A year of utility bills can help adjust the model, although some buildings cannot yet be matched successfully."],
  ["Compare improvements", "We estimate each upgrade’s cost and savings, then consider how upgrades work together. Solar is sized after the other selected improvements reduce demand. Your plan separates upgrades within your budget from options needing more money and explains why other options were left out."],
  ["Review before you decide", "Read the savings range, evidence and checks alongside the headline estimate. Confirm important measurements, your utility prices and contractor quotes before committing. Any draft paperwork needs its own review before signing."],
];
const sources = [
  ["Inside your home", "Matterport", "Interior scans provide room measurements and photographs. Anything inferred from an image remains an estimate."],
  ["Your roof and surroundings", "Vexcel", "Aerial photographs and survey records provide building outlines and roof information. Roof shape and slope may still need an on-site check."],
  ["Property details", "CoStar", "Property records provide details such as building age, use and floor area. Records can differ from the building today."],
  ["Weather and sunshine", "Weather station records and public solar data", "Local weather drives the energy estimate. A second solar model provides a comparison, which does not prove actual solar production."],
  ["Energy prices and comparisons", "U.S. Energy Information Administration and public building surveys", "Published prices and energy surveys provide context. State average prices do not replace your own utility bill."],
];
export default function HowItWorks({ onExplore }: { onExplore?: (view: "evals" | "solar-map") => void }) {
  return <section className="how-it-works">
    <div className="section-heading"><div><span className="eyebrow">HOW IT WORKS</span><h2>From your property to a practical plan.</h2></div><BookOpen size={26}/></div>
    <p className="section-description">Understand what goes into your estimate, where the information comes from and what to check before spending money.</p>
    {onExplore && <div className="hiw-explore"><button className="secondary-button" onClick={() => onExplore("evals")}>See accuracy &amp; evidence</button><button className="secondary-button" onClick={() => onExplore("solar-map")}>Explore the Solar map</button></div>}
    <h3><Workflow size={20}/> How we build your plan</h3>
    <ol className="hiw-stages">{steps.map(([title,body]) => <li key={title}><strong>{title}</strong><p>{body}</p></li>)}</ol>
    <h3><Database size={20}/> Where the information comes from</h3>
    <div className="source-explainer-grid">{sources.map(([title,source,body]) => <article key={title}><span className="eyebrow">{source}</span><h4>{title}</h4><p>{body}</p></article>)}</div>
    <section className="honesty-note"><h3>Estimates have limits</h3><p>The savings and cost ranges are model estimates and have not been shown to capture every source of uncertainty. Current accuracy studies do not establish savings accuracy for your specific home. Daylight comparisons are exploratory. The Accuracy &amp; evidence page shows completed studies, their limitations and checks that have not been run yet.</p></section>
  </section>;
}
