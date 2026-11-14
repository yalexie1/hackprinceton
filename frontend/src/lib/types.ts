// Browser contract mirrors specs/SPEC.md section 9 (schema 0.3.1).
export const SCHEMA_VERSION = "0.3.1";
export interface Ranged {
  low: number;
  expected: number;
  high: number;
  unit: string;
}
export interface EvidenceRef {
  kind: string;
  ref: string;
  note?: string | null;
}
export interface PropertySummary {
  sid: string;
  name: string;
  segment: "residential" | "commercial";
  use_type: string;
  address?: string | null;
  city?: string | null;
  state?: "CA" | "TX" | null;
  lat?: number | null;
  lon?: number | null;
  costar_property_id?: string | null;
  costar_listing_id?: string | null;
  costar_residential_listing_id?: string | null;
  has_splat: boolean;
  has_defurnished: boolean;
  pano_count: number;
  room_count: number;
  floor_count: number;
}
export interface Assumption {
  key: string;
  label: string;
  value: Ranged | string | boolean;
  source: string;
  confidence: number;
  evidence: EvidenceRef[];
  user_editable: boolean;
}
export interface Flag {
  key: string;
  status: string;
  message: string;
  added_cost_usd?: Ranged | null;
  evidence: EvidenceRef[];
}
export interface EnergyUse {
  electricity_kwh: Ranged;
  gas_kwh: Ranged;
  cost_usd: Ranged;
  co2_kg: Ranged;
  co2_nonbaseload_kg?: Ranged | null;
}
export interface FinancingScenario {
  kind: "cash" | "cpace";
  eligible: boolean;
  financed_usd: number;
  rate?: number | null;
  term_years?: number | null;
  program_sir?: number | null;
  annual_payment_usd: number;
  net_cashflow_year1_usd: Ranged;
  notes: string[];
}
export interface FinancialBreakdown {
  installed_cost_usd: Ranged;
  cost_source: string;
  incentives: {
    name: string;
    kind: string;
    amount_usd: Ranged;
    status: string;
    eligibility?: "confirmed" | "needs_confirmation" | "not_eligible";
    conditions?: string[];
    citation: string;
  }[];
  net_upfront_usd: Ranged;
  annual_savings_usd: Ranged;
  annual_om_change_usd: number;
  useful_life_years: number;
  simple_payback_years?: Ranged | null;
  discounted_payback_years?: number | null;
  npv_usd: Ranged;
  npv_sensitivity_usd?: number | null;
  sir?: number | null;
  irr?: number | null;
  airr?: number | null;
  discount_rate: number;
  electricity_escalation: number;
  gas_escalation: number;
  analysis_period_years: number;
  financing: FinancingScenario[];
}
export interface Anchor {
  room_id?: string | null;
  pano_id?: string | null;
  x?: number | null;
  y?: number | null;
  z?: number | null;
  label: string;
}
export interface SolarDesign {
  system_kw_dc: number;
  panel_count: number;
  panels: {
    plane_id: string;
    polygon_wkt?: string | null;
    annual_kwh: number;
    shading_loss_fraction: number;
  }[];
  annual_kwh: Ranged;
  self_consumption_fraction?: number | null;
  electrical: Flag;
  structural: Flag;
}
export interface DeskScore {
  room_id: string;
  x: number;
  y: number;
  daylight: number;
  glare_risk: number;
  comfort_ppd: number;
  score: number;
  recommended: boolean;
  daylight_factor?: number | null;
  view_azimuth_deg?: number | null;
  direct_sun_hours?: number | null;
  max_dt_pr_k?: number | null;
  warnings?: string[];
}
export interface ValueUplift {
  value_usd: Ranged;
  method: string;
  cap_rate?: Ranged | null;
  comp_count: number;
  notes: string[];
}
export interface MeasureResult {
  measure_id: string;
  title: string;
  applicable: boolean;
  not_applicable_reason?: string | null;
  description: string;
  params: Record<string, unknown>;
  savings?: EnergyUse | null;
  finance?: FinancialBreakdown | null;
  flags: Flag[];
  anchors: Anchor[];
  evidence: EvidenceRef[];
  formula_ids: string[];
  solar?: SolarDesign | null;
  layout?: {
    candidates: DeskScore[];
    desks_requested: number;
    window_source?: "measured" | "vision" | null;
    target_lux?: number | null;
    setpoint_lux?: number | null;
    control_type?: string | null;
    score_weights?: Record<string, number>;
    occupied_hours_per_year?: number | null;
    lighting_kwh_saved?: Ranged | null;
    warnings?: string[];
  } | null;
  value_uplift?: ValueUplift | null;
  warnings: string[];
}
export interface Plan {
  budget_usd: number;
  selected: {
    rank: number;
    measure: MeasureResult;
    cumulative_upfront_usd: number;
    remaining_budget_usd: number;
  }[];
  financeable: MeasureResult[];
  skipped: { measure_id: string; reason: string; detail: string }[];
  total_upfront_usd: Ranged;
  total_annual_savings_usd: Ranged;
  total_co2_kg: Ranged;
  baseline_after: EnergyUse;
  value_uplift?: ValueUplift | null;
}
export type Role = "owner_occupier" | "landlord" | "tenant";
export interface RunRequest {
  sid: string;
  budget_usd: number;
  role: Role;
  bills?: { electricity_kwh: number[]; gas_kwh?: number[] } | null;
  overrides?: Record<string, number | string | boolean>;
  desks_requested?: number | null;
}
export interface Question {
  id: string;
  assumption_key: string;
  prompt: string;
  choices: { label: string; value: number | string | boolean | null }[];
  impact_note: string;
}
export interface RunEvent {
  type:
    | "stage_started"
    | "stage_done"
    | "todo"
    | "tool_call"
    | "fallback"
    | "question"
    | "partial_result"
    | "error"
    | "done";
  stage?: string | null;
  message: string;
  payload: Record<string, unknown>;
}
export interface RunResult {
  schema_version: string;
  run_id: string;
  status: "running" | "waiting_for_user" | "done" | "error";
  request: RunRequest;
  property: PropertySummary;
  building_model?: {
    schema_version: string;
    sid: string;
    assumptions: Assumption[];
    flags: Flag[];
    roof_planes: {
      id: string;
      polygon_wkt: string;
      area_m2: number;
      tilt_deg: Ranged;
      azimuth_deg: number;
      usable_area_m2: number;
      geometry_source: string;
    }[];
    zones: {
      id: string;
      room_ids: string[];
      use: string;
      floor_area_m2: number;
      volume_m3: number;
      conditioned: boolean;
    }[];
  } | null;
  baseline?: {
    annual: EnergyUse;
    end_use_kwh: Record<string, number>;
    monthly_electricity_kwh: number[];
    monthly_gas_kwh: number[];
    peak_cooling_w: number;
    peak_heating_w: number;
    calibrated_to_bills: boolean;
  } | null;
  measures: MeasureResult[];
  plan?: Plan | null;
  questions: Question[];
  narrative_md: string;
  warnings: string[];
}
export type DocType =
  | "retrofit_contract_residential"
  | "retrofit_contract_commercial"
  | "solar_installation_agreement"
  | "bid_package_rfp"
  | "energy_savings_guarantee"
  | "cpace_package";
export interface DocumentRequest {
  run_id: string;
  doc_type: DocType;
  state: "CA" | "TX";
  measure_ids: string[];
  fields: Record<string, string>;
}
export interface DocumentDraft {
  doc_id: string;
  doc_type: DocType;
  state: "CA" | "TX";
  markdown: string;
  unfilled_placeholders: string[];
  statutory_checks: {
    requirement_id?: string | null;
    requirement: string;
    citation: string;
    satisfied: boolean;
    note?: string | null;
  }[];
  disclaimer: string;
}
