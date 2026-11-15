import type { Assumption, EvidenceRef, RunEvent } from "./types";
import { MEASURE_NAMES } from "../components/FindingReason";
import { auditStageLabel } from "./format";

const INPUT_NAMES: Record<string, string> = {
  "geometry.north_offset_deg": "Building orientation",
  "geometry.ceiling_height_m": "Ceiling height",
  "building.year_built": "Year built", "building.stories": "Floors above ground",
  "building.gross_area_m2": "Total building area", "building.floor_plate_m2": "Area per floor",
  "window.area_m2": "Total window area", "window.type": "Window glass and frame",
  "window.u_value": "Heat passing through windows", "window.shgc": "Sunlight heat passing through windows",
  "window.shading": "Window shades", "hvac.system_type": "Heating and cooling system",
  "hvac.thermostat_type": "Thermostat type", "lighting.fixture_type": "Light bulbs",
  "wall.material": "Interior wall material", "electrical.outlet_type": "Electrical outlets",
  "electrical.service_amps": "Main electrical capacity", "tariff.electricity_usd_per_kwh": "Electricity price",
  "roof.material": "Roof material", "roof.shape": "Roof shape", "roof.existing_solar": "Solar panels already installed",
  "roof.tilt_deg": "Estimated roof slope", "roof.ridge_direction": "Assumed direction of the roof ridge",
  "roof.obstruction_allowance_m2": "Roof space reserved around vents and other features",
  "roof.fire_setbacks": "Roof access space for firefighters", "roof.usable_area_m2": "Estimated roof space available for panels",
  "roof.absorptance": "Share of sunlight absorbed by the roof", "wall.u_value": "Heat passing through exterior walls",
  "roof.u_value": "Heat passing through the attic ceiling", "infiltration.ach50": "Air leakage in a pressure test",
  "hvac.heating_fuel": "Heating fuel", "hvac.cooling_rating": "Air-conditioning efficiency rating",
  "hvac.heating_rating": "Furnace efficiency", "hvac.distribution_efficiency": "Share of heat delivered through the ducts",
  "hvac.duct_location": "Duct location", "dhw.type": "Water heater type", "dhw.fuel": "Water heater fuel",
  "dhw.uef": "Water heater efficiency", "setpoint.heating": "Heating thermostat temperature",
  "setpoint.cooling": "Cooling thermostat temperature", "lighting.lpd": "Lighting power per unit of floor area",
  "plug.ppd": "Appliance power per unit of floor area", "occupancy.count": "People using the building",
};
const WORDS: Record<string, string> = {
  single_clear_non_metal: "Single-pane clear glass in a non-metal frame",
  single_clear_metal: "Single-pane clear glass in a metal frame",
  central_ac_furnace: "Central air conditioning with a furnace", interior_blinds: "Indoor blinds or shades",
  two_prong: "Two-prong outlets", three_prong: "Three-prong outlets", long_side: "Along the longer side of the building",
  incandescent: "Incandescent bulbs", storage: "Storage-tank water heater", gable: "Gable roof",
  single_family: "Single-family home", needs_confirmation: "Needs confirmation", not_eligible: "Not eligible",
  vexcel_parametric: "Estimated from aerial records and the roof shape", published_default: "Published reference estimate",
  vintage_default: "Estimate based on building age", gas: "Natural gas", smart: "Smart thermostat",
  manual: "Manual thermostat", attic: "Attic", shingle: "Shingles", plaster: "Plaster",
};
export function inputName(key: string, label = ""): string {
  if (label.includes(" ") && !/U-value|SHGC|AFUE|SEER|HVAC|coefficient|density|setpoint|\[U\]|ROOF-|50 Pa|above grade|floor plate|solar absorptance|model \+y|marginal|distribution efficiency/i.test(label)) return readableText(label);
  return INPUT_NAMES[key] || readableText(label || key);
}
export function readableText(input: string): string {
  if (WORDS[input.trim()]) return WORDS[input.trim()];
  let text = String(input || "");
  for (const [key, name] of Object.entries({ ...MEASURE_NAMES, ...INPUT_NAMES, ...Object.fromEntries(Object.entries(WORDS).filter(([key]) => key.includes("_"))) }).sort((a,b) => b[0].length-a[0].length)) {
    text = text.replace(new RegExp(`\\b${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g"), name);
  }
  text = text
    .replace(/\b[A-Z]{2,8}-\d{2}\b/g, "the documented method")
    .replace(/\bSPEC\.md(?: section [\d.]+)?/gi, "the documented method")
    .replace(/the source's/g, "the published reference's")
    .replace(/\bHVAC\b/g, "heating and cooling")
    .replace(/\ba PV array\b/gi, "solar panels")
    .replace(/\bPV array\b/gi, "solar panels")
    .replace(/\bPV\b/g, "solar")
    .replace(/\bDC\b/g, "panel capacity")
    .replace(/\bCPI-U adjusted\b/g, "adjusted for consumer-price inflation")
    .replace(/\bUSD\b/g, "U.S. dollars")
    .replace(/\bCOST row\b/g, "published installation price")
    .replace(/\bcentral(?= with the)/g, "expected cost")
    .replace(/\bengineering judgment\b/gi, "an estimate that needs checking")
    .replace(/\bbenchmarked baseline\b/gi, "survey-adjusted energy estimate")
    .replace(/\bbaseline\b/g, "current energy estimate")
    .replace(/\b(?:U from|U changes from) ([\d.]+) to ([\d.]+)/g, "heat-transfer rating from $1 to $2")
    .replace(/\bcues:/g, "visible signs:")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/(?:specs|backend|frontend|data)\/[\w./-]+/g, "the supporting source")
    .replace(/\b[A-Z]{2,8}-\d{2}(?:\s+to\s+[A-Z]{2,8}-\d{2})?\b/g, "the calculation method")
    .replace(/\b(?:physics\s+0[1-4]|\[U\])/gi, "")
    .replace(/\b[a-zA-Z0-9]{22,}\b/g, "a recorded building view")
    .replace(/\b([a-z][a-z0-9]*[._][a-z][a-z0-9_.]*)\b/g, (token) => token.replace(/[._]/g, " "))
    .replace(/\bSIR\b/g, "lifetime savings divided by cost")
    .replace(/\bNPV\b/g, "lifetime benefit in today’s dollars")
    .replace(/\bIRR\b/g, "annual rate of return")
    .replace(/\bAFUE\b/g, "furnace efficiency")
    .replace(/\bSHGC\b/g, "share of sunlight heat passing through the glass")
    .replace(/\bU-value\b/gi, "heat-transfer rating")
    .replace(/\bquaternion(?:'s)? sense\b/gi, "scan orientation")
    .replace(/\bgeoreference\b/gi, "map location")
    .replace(/\bfootprint\b/gi, "building outline")
    .replace(/\bparametric\b/gi, "estimated from the roof shape")
    .replace(/\bplug loads\b/gi, "appliance and electronics use")
    .replace(/\bsetpoint\b/gi, "thermostat temperature")
    .replace(/\bUSD\/kWh\b/g, "dollars per kilowatt-hour")
    .replace(/\bW\/m2K\b/g, "watts per square metre per degree of temperature difference")
    .replace(/\bW\/m2\b/g, "watts per square metre")
    .replace(/\bm2\b/g, "m²")
    .replace(/\s+([,;.])/g, "$1")
    .replace(/the the (?:calculation|documented) method/g, "the documented method")
    .replace(/\(\s*the calculation method\s*\)/g, "")
    .replace(/ {2,}/g, " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}
export function warningText(text: string): string {
  if (/Uses the LED efficacy ratio/i.test(text)) return "Lighting savings depend on the assumed efficiency of the existing bulbs and replacement LEDs. These efficiencies are model inputs, not measurements of the installed lamps.";
  if (/Assumes 2x4 wood framing at 16 in/i.test(text)) return "The insulation estimate assumes wood framing made from two-by-four studs spaced 16 inches apart. The predicted heat transfer uses a published wall example, rather than a measurement of this wall.";

  if (/No splat/i.test(text)) return "A detailed 3D roof scan is unavailable. The roof estimate uses aerial survey information instead.";
  if (/quaternion sense not decidable/i.test(text)) return "The interior scan and aerial outline do not uniquely confirm the building’s direction. Check its orientation before relying on sunlight or panel-placement estimates.";
  if (/vexcel property\/extract:structure/i.test(text)) {
    const area = /chose\s+(\d+(?:\.\d+)?)\s*m2/.exec(text)?.[1];
    const reference = /from\s+(?:the\s+)?(\d+(?:\.\d+)?)\s*m2 CoStar/.exec(text)?.[1];
    const difference = /(\d+)%\s*from/.exec(text)?.[1];
    const date = /\((\d{4}-\d{2}-\d{2})\)/.exec(text)?.[1];
    return area && reference && difference
      ? `The selected aerial building outline covers ${area} m², compared with ${reference} m² per floor in the property record: a ${difference}% difference. ${date ? `The chosen aerial capture is dated ${date}. ` : ""}Several captures and candidate outlines were compared. Confirm the correct roof boundary before a final solar design.`
      : readableText(text);
  }
  if (/tariff eia\/retail-sales/i.test(text)) return `Electricity costs use a state average for homes, rather than this property’s electricity bill. Source: the U.S. Energy Information Administration${text.match(/\d{4}-\d{2}/) ? `, ${text.match(/\d{4}-\d{2}/)![0]}` : ""}. Confirm your utility rate before deciding.`;
  if (/tariff eia\/natural-gas-price/i.test(text)) return `Gas costs use a state average delivered price for homes, rather than this property’s gas bill. Source: the U.S. Energy Information Administration${text.match(/\b20\d{2}\b/) ? `, ${text.match(/\b20\d{2}\b/)![0]}` : ""}. Confirm your utility rate before deciding.`;
  return readableText(text);
}
const SOURCES: Record<string, string> = {
  pano: "Interior photographs", matterport_field: "Interior building scan", costar_field: "CoStar property record",
  vexcel_attr: "Aerial survey record", default_table: "Published reference or stated estimate",
  user: "Information provided during the audit", formula: "Calculation method", weather: "Weather records",
};
export function evidenceText(e: EvidenceRef): string {
  const source = SOURCES[e.kind] || readableText(e.kind) || "Recorded source";
  let note = e.note || "";
  const objectName: Record<string,string> = {"ac-unit":"Rooftop air-conditioning units",chimney:"Chimneys","roof-vent":"Roof vents","satellite-dish":"Satellite dishes",skylight:"Skylights"};
  const object = /^roof-objects\.([\w-]+)\.count$/.exec(e.ref);
  if (object && /^\d+$/.test(note)) note = `${objectName[object[1]] || "Roof features"} recorded in the aerial survey: ${note}. Counts are not an on-site inspection.`;
  if (!note && e.ref === "ROOF-03") note = "Roof slope is estimated from a published range for this roof shape, rather than measured at this property.";
  if (!note && e.ref === "ROOF-05") note = "The ridge is assumed to follow the longer side of the building. This needs checking; the alternative turns the roof sections by 90 degrees.";
  if (!note && e.ref === "ROOF-04") note = "Available roof space uses estimated clearance allowances around roof features. Confirm these with an installer.";
  if (!note && e.ref === "ROOF-06") note = "Access space follows an initial fire-code interpretation. The local fire authority must confirm the requirements.";
  const windowTypes = /^properties of (\w+) read as vision; high is (\w+)/.exec(note);
  if (windowTypes) note = `Reference values for ${readableText(windowTypes[1]).toLowerCase()}, inferred from photographs. The upper estimate allows for ${readableText(windowTypes[2]).toLowerCase()}. Confirm the glass and frame on site.`;
  if (/have no height in the scan/.test(note)) note = "Some rooms have no recorded ceiling height. Their height is estimated from the average of the measured rooms.";
  if (/from the yearBuilt event/.test(note) && /kit field names/.test(note)) note = "The construction year comes from the property record.";
  if (/footprint cannot tell the quaternion/.test(note)) note = "The scan and aerial outline allow more than one building orientation. The direction remains uncertain.";
  note = note.replace(/from the yearBuilt event: widened to the adjacent vintage rows/g, "the range also includes nearby building-age groups because equipment and insulation have not been confirmed")
    .replace(/follows the system type/g, "Assumed from the heating and cooling system")
    .replace(/shape class '([^']+)'/g, "Roof shape recorded as $1")
    .replace(/read as vision/g, "inferred from photographs")
    .replace(/; cues:/g, "; visible signs:");
  return `${source}${note ? `: ${readableText(note)}` : "."}`;
}
export function assumptionSummary(a: Assumption): string {
  const sources = [...new Set(a.evidence.map(e => SOURCES[e.kind] || readableText(e.kind)))].join("; ");
  const notes = a.evidence.map(e => e.note || "").join(" ");
  let explanation = "Full source observations are available on the Assumptions page in the app.";
  if (a.key === "geometry.north_offset_deg" && /cannot tell|quaternion|not decidable/i.test(notes)) explanation = "The scan and aerial outline allow more than one building direction. Confirm the orientation before relying on sunlight or solar placement.";
  else if (a.key === "electrical.service_amps" && /panel not visible|no panel/i.test(notes)) explanation = "The main electrical panel was not visible. Capacity is inferred from indirect clues, not a verified panel rating. An electrician must confirm it.";
  else if (a.key === "roof.tilt_deg" && a.evidence.some(e => e.ref === "ROOF-03")) explanation = "Slope is estimated from the roof shape and a published range, not measured at this property.";
  else if (a.key === "roof.ridge_direction" && a.evidence.some(e => e.ref === "ROOF-05")) explanation = "The ridge direction is assumed and needs an on-site check. Changing it can turn the roof sections by 90 degrees.";
  else if (a.key === "roof.obstruction_allowance_m2" && a.evidence.some(e => e.ref === "ROOF-04")) explanation = a.evidence.filter(e => /^roof-objects\..+\.count$/.test(e.ref)).map(evidenceText).join(" ") + " Space reserved around these objects is an estimate; confirm it with an installer.";
  else if (a.key === "roof.fire_setbacks" && a.evidence.some(e => e.ref === "ROOF-06")) explanation = "Roof access space uses an initial interpretation of fire-code requirements. The local fire authority must confirm it.";
  else if (a.source === "vision") explanation = "Inferred from photographs. Image observations can be incomplete or disagree; confirm this detail on site before relying on it.";
  else if (["vintage_default", "published_default"].includes(a.source)) explanation = "Uses a published reference or stated estimate, rather than a measurement of this equipment or building detail. Confirm it before final design.";
  else if (a.key === "geometry.ceiling_height_m" && /have no height/.test(notes)) explanation = "Some rooms have no recorded ceiling height. Their height is estimated from the average of measured rooms.";
  return `${sources || "No source recorded"}. ${explanation}`;
}

const TOOLS: Record<string, string> = {
  get_property_bundle: "Gathering the property record, interior scan and aerial survey",
  detect_roof_elements: "Reviewing the roof outline and possible roof features",
  observe_interior: "Reviewing interior photographs for visible building details",
  build_building_model: "Combining measured details and estimates into a building model",
  run_baseline: "Estimating the building’s current energy use",
  build_plan: "Comparing improvements and assembling a plan for your budget",
  evaluate_measures: "Comparing potential energy-saving improvements",
  explain_run: "Writing a summary of the findings", draft_document: "Preparing the requested draft document",
};
export function auditEventText(event: RunEvent): string {
  if (event.type === "todo") return "Updating the audit checklist";
  if (event.type === "tool_call") return TOOLS[event.message] || `${auditStageLabel(event.stage || "tool_call")}: reviewing the next part of your property`;
  return warningText(event.message || String(event.payload.detail || event.payload.fallback || "Your audit has a new update."));
}
export function friendlyUnit(unit: string): string {
  return ({ m2: "m²", deg: "degrees", C: "°C", A: "amps", storeys: "floors", "-": "", "W/m2": "W/m²", "W/m2K": "W/m²K", "1/h at 50 Pa": "air changes per hour at test pressure", "USD/kWh": "dollars per kWh" } as Record<string,string>)[unit] ?? unit;
}

/** Display a fraction as a percentage without changing the stored model input. */
export function assumptionDisplay(a: Assumption): { value: string; range: string } {
  if (typeof a.value !== "object") return {value: typeof a.value === "boolean" ? a.value ? "Yes" : "No" : readableText(a.value), range:"Current setting"};
  const percent = isPercentageInput(a.key);
  const unit = percent ? "%" : a.value.unit === "year" ? "" : a.value.unit === "storeys" && a.value.expected === 1 ? "floor" : friendlyUnit(a.value.unit);
  const groupDigits = a.value.unit !== "year";
  const format = (n: number) => new Intl.NumberFormat("en-US",{maximumFractionDigits:2,useGrouping:groupDigits}).format(n * (percent ? 100 : 1));
  return {value: `${format(a.value.expected)}${percent ? "" : " "}${unit}`.trim(), range:a.value.low === a.value.high ? "Single value recorded; review the source below" : `${format(a.value.low)} to ${format(a.value.high)}${percent ? "" : " "}${unit} (estimated range)`.trim()};
}

export function isPercentageInput(key: string): boolean {
  return ["window.shgc","roof.absorptance","hvac.heating_rating","hvac.distribution_efficiency","dhw.uef"].includes(key);
}
