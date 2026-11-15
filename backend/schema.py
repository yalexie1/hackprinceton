from __future__ import annotations
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "0.3.8"

# ---------- primitives ----------

class Ranged(BaseModel):
    """A quantity with uncertainty. low <= expected <= high.

    expected is the result at expected inputs. For an input, low and high are
    judged 10th and 90th percentiles. For a modelled output, low and high are
    the range the input ranges produce (physics UNC-01, UNC-02); they are not
    hard bounds and not a measured 80 % interval.
    """
    low: float
    expected: float
    high: float
    unit: str

    @model_validator(mode="after")
    def _ordered(self) -> "Ranged":
        if not (self.low <= self.expected <= self.high):
            raise ValueError("Ranged requires low <= expected <= high")
        return self

Source = Literal["user", "measured", "costar", "vexcel", "vision", "published_default", "vintage_default"]

class EvidenceRef(BaseModel):
    kind: Literal["pano", "ortho", "oblique", "matterport_field", "vexcel_attr",
                  "costar_field", "default_table", "user"]
    ref: str                      # pano id, attribute key, table id, ...
    note: Optional[str] = None

class Assumption(BaseModel):
    key: str                      # e.g. "wall.u_value", "hvac.cooling_cop"
    label: str
    value: Union[Ranged, str, bool]
    source: Source
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceRef] = []
    user_editable: bool = True

class Flag(BaseModel):
    key: str                      # e.g. "electrical.service"
    status: Literal["likely_ok", "likely_upgrade", "blocked", "unknown"]
    message: str
    added_cost_usd: Optional[Ranged] = None
    evidence: list[EvidenceRef] = []

# ---------- data lane ----------

Segment = Literal["residential", "commercial"]
UseType = Literal["single_family", "multifamily_unit", "office", "retail", "other", "unknown"]

class PropertySummary(BaseModel):
    sid: str                      # Matterport model id
    name: str
    segment: Segment
    use_type: UseType
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[Literal["CA", "TX"]] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    costar_property_id: Optional[str] = None             # kit PropertyId (commercial)
    costar_listing_id: Optional[str] = None              # kit ListingId (residential)
    costar_residential_listing_id: Optional[str] = None  # groups the listings of one sale or rental
    has_splat: bool = False
    has_defurnished: bool = False
    pano_count: int = 0
    room_count: int = 0
    floor_count: int = 0

class Vertex(BaseModel):
    id: str
    x: float                      # metres, model frame
    y: float

class Opening(BaseModel):
    """A door or window in a wall edge, as measured by the scan."""
    id: str
    type: str                     # OpeningType: "divider", "doorway", "opening", "window"
    label: Optional[str] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    lower_elevation_m: Optional[float] = None   # bottom of the opening above the floor (sill height)
    relative_center: Optional[float] = Field(default=None, ge=0, le=1)   # NOT metres: centre as a fraction of
                                                # the edge length; centre in metres = relative_center * edge length.
                                                # Which vertex it is measured from is [P] Data lane

class WallEdge(BaseModel):
    id: str
    type: str                     # EdgeType: "wall" or "invisible"; doors and windows are openings
    thickness_m: Optional[float] = None
    vertex_ids: tuple[str, str]
    openings: list[Opening] = []

class Floor(BaseModel):
    id: str
    label: str
    vertices: list[Vertex]
    edges: list[WallEdge]

class Room(BaseModel):
    id: str
    floor_id: str
    label: Optional[str] = None   # Matterport classification
    label_confidence: Optional[float] = None
    area_m2: Optional[float] = None
    width_m: Optional[float] = None
    depth_m: Optional[float] = None
    height_m: Optional[float] = None
    boundary_edge_ids: list[str] = []
    polygon: list[tuple[float, float]] = []    # room outline in the model frame, metres, in order

class Pano(BaseModel):
    id: str
    label: Optional[str] = None
    x: float
    y: float
    z: float
    face_paths: list[str] = []    # six cached cube faces: up, four sides, down
    defurnished_face_paths: list[str] = []

class FloorplanAsset(BaseModel):
    format: str
    flags: list[str] = []
    path: str
    resolution_px_per_m: Optional[float] = None
    origin_x: Optional[float] = None
    origin_y: Optional[float] = None

class Quaternion(BaseModel):
    x: float
    y: float
    z: float
    w: float

class GeoReference(BaseModel):
    """Model.geocoordinates from the Model API. Places and rotates the model frame on the earth."""
    latitude: float
    longitude: float
    altitude_m: Optional[float] = None
    rotation: Quaternion                        # as returned; about z for a level model
    translation: Optional[tuple[float, float, float]] = None
    source: Optional[str] = None                # GeoCoordinateSource: "client", "processing", "unknown"

class MatterportData(BaseModel):
    georeference: Optional[GeoReference] = None
    floors: list[Floor]
    rooms: list[Room]
    panos: list[Pano]
    floorplans: list[FloorplanAsset] = []
    ai_summary: Optional[str] = None
    capture_notes: Optional[str] = None
    property_classifications: list[str] = []
    matterpak_available: bool = False
    mesh_path: Optional[str] = None
    point_cloud_path: Optional[str] = None
    splat_path: Optional[str] = None
    drone_photo_paths: list[str] = []
    defurnished_view_id: Optional[str] = None

class VexcelStructure(BaseModel):
    primary: bool = False
    footprint_wkt: Optional[str] = None
    footprint_area_m2: Optional[float] = None
    attributes: dict[str, Union[str, float, bool, None]] = {}   # flat dotted keys as returned

class VexcelDetection(BaseModel):
    label: str
    confidence: float
    image_id: str                               # e.g. "ortho-1", "oriented-1"
    bbox_wkt: str                               # map-coordinate polygon, as returned
    pixel_bbox: Optional[tuple[int, int, int, int]] = None   # x, y, w, h in the image
    mask_png_path: Optional[str] = None         # cached pixel mask, cropped to pixel_bbox
    mask_wkt: Optional[str] = None              # map polygon derived from the pixel mask
    mask_area_m2: Optional[float] = None        # ground area of the mask itself (pixel count x pixel ground area), not of its box or hull

class VexcelData(BaseModel):
    collection: Optional[str] = None
    parcel_wkt: Optional[str] = None
    attributes: dict[str, Union[str, float, bool, None]] = {}
    structures: list[VexcelStructure] = []
    ortho_path: Optional[str] = None
    oblique_paths: dict[str, str] = {}        # direction -> path
    detections: list[VexcelDetection] = []

class Tenancy(BaseModel):
    """One tenant in the building, from location-occupancy joined to company-detail."""
    tenant_name: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None
    area_m2: Optional[float] = None
    floor: Optional[str] = None
    move_in: Optional[str] = None              # ISO date
    move_out: Optional[str] = None             # ISO date; None = still in place

class OccupancyData(BaseModel):
    tenancies: list[Tenancy] = []
    employees_total: Optional[int] = None
    occupied_area_m2: Optional[float] = None

class MarketData(BaseModel):
    """Inputs to value uplift, from commercial-sale-comp and apartment-listing."""
    cap_rate: Optional[Ranged] = None                     # fraction per year, from comparable sales
    sale_price_usd_per_m2: Optional[Ranged] = None
    asking_rent_usd_per_m2_year: Optional[Ranged] = None
    comp_count: int = 0

class CostarData(BaseModel):
    kind: Literal["residential_listing", "commercial_property"]
    # join keys from the kit's starter CSVs; the join is on matterport_model_id
    matterport_model_id: str
    property_id: Optional[str] = None          # PropertyId, commercial
    listing_id: Optional[str] = None           # ListingId, residential
    residential_listing_id: Optional[str] = None
    parent_ids: list[str] = []                 # every PropertyId or ListingId this model is attached to; one
                                               # scan can belong to several (307 model ids do); the ids above are
                                               # the primary by the Data lane's documented rule
    record_id: str                             # `id` of the JSONL record
    raw: dict                                  # the record as found in the kit
    # normalised fields; names in the kit's models/ and schemas/ are authoritative
    property_type: Optional[str] = None        # enum name, e.g. "Office"
    property_type_code: Optional[int] = None   # propertyType enum value; Office = 5
    year_built: Optional[int] = None           # from constructionEvents[], ConstructionComplete preferred
    year_built_event: Optional[str] = None     # which construction event year_built came from
    year_renovated: Optional[int] = None
    building_class: Optional[str] = None       # "A", "B", "C", "F"
    building_area_m2: Optional[float] = None   # gross building area; use for the envelope
    rentable_area_m2: Optional[float] = None   # leasing only
    stories: Optional[int] = None
    owner_name: Optional[str] = None
    occupancy: Optional[OccupancyData] = None
    market: Optional[MarketData] = None

class ClimateSite(BaseModel):
    lat: float
    lon: float
    timezone: str
    climate_zone: Optional[str] = None
    weather_path: str                          # typical-year hourly file in the cache
    weather_source: str
    weather_time_convention: Optional[str] = None   # what an hourly stamp means: "hour_start", "hour_end", "hour_centre"
    pvgis_annual_kwh_per_kw: Optional[float] = None # cross-check only
    pvgis_sd_fraction: Optional[float] = None       # inter-annual standard deviation / annual yield

class Tariff(BaseModel):
    utility: str
    electricity_usd_per_kwh: float             # marginal price, with per-kWh riders and taxes
    gas_usd_per_kwh: Optional[float] = None    # per kWh of higher heating value; 1 therm = 29.3071 kWh
    export_usd_per_kwh: Optional[float] = None # None where no export price is mandated (Texas)
    export_regime: Optional[Literal["net_metering", "net_billing", "none"]] = None
    fixed_usd_per_month: float = 0.0
    source: str
    retrieved: str                             # ISO date

class FetchRecord(BaseModel):
    layer: Literal["matterport", "vexcel", "costar", "weather", "tariff", "place"]   # place: incorporated-place and program-area lookups
    what: str
    status: Literal["ok", "missing", "locked", "error", "fallback"]
    detail: Optional[str] = None

class PropertyBundle(BaseModel):
    schema_version: str = SCHEMA_VERSION
    summary: PropertySummary
    matterport: MatterportData
    vexcel: Optional[VexcelData] = None
    costar: Optional[CostarData] = None
    climate: ClimateSite
    tariff: Tariff
    provenance: list[FetchRecord] = []

# ---------- analysis lane ----------

class Surface(BaseModel):
    id: str
    zone_id: str
    kind: Literal["wall", "roof", "floor", "window", "door"]
    boundary: Literal["exterior", "ground", "adjacent_conditioned", "adjacent_unconditioned"]
    area_m2: float
    azimuth_deg: Optional[float] = None        # 0 = north, clockwise; None for horizontal
    tilt_deg: float                            # 0 = horizontal facing up, 90 = vertical
    u_value: Ranged                            # W/m2K
    shgc: Optional[Ranged] = None              # windows only
    visible_transmittance: Optional[Ranged] = None   # windows only; daylight needs it, shgc is not enough
    parent_surface_id: Optional[str] = None    # window -> wall
    source_edge_id: Optional[str] = None       # WallEdge this surface was built from
    source_opening_id: Optional[str] = None    # Opening this window or door was built from; None = from vision
    solar_absorptance: Optional[Ranged] = None # opaque exterior surfaces (physics ENV-05)
    emittance: Optional[float] = None
    exposed_perimeter_m: Optional[float] = None   # ground floors (physics ENV-04)

class Zone(BaseModel):
    id: str
    room_ids: list[str]
    use: str
    floor_area_m2: float
    volume_m3: float
    conditioned: bool = True
    mass_class: Literal["very_light", "light", "medium", "heavy", "very_heavy"] = "medium"   # physics ZON

class Systems(BaseModel):
    hvac_type: Literal["central_ac_furnace", "heat_pump", "rooftop_unit", "room_ac", "central_plant",
                       "none", "unknown"]
    heating_fuel: Literal["electricity", "gas", "none", "unknown"]
    cooling_cop: Ranged                        # seasonal, W/W
    heating_efficiency: Ranged                 # seasonal: COP for heat pumps, fraction for furnaces
    dhw_type: Literal["storage", "tankless", "heat_pump", "unknown"]
    dhw_fuel: Literal["electricity", "gas", "unknown"]
    dhw_efficiency: Ranged
    lighting_w_per_m2: Ranged
    plug_w_per_m2: Ranged
    infiltration_ach: Ranged                   # annual mean air changes per hour, a reported result
    occupancy_schedule: str                    # "home", "office" or "office_vacant" (physics DEF)
    occupants: Optional[Ranged] = None         # people; from CoStar tenancies when present
    # optional detail the thermal spec uses when known (specs/physics/02-thermal-systems.md section 12)
    infiltration_ach50: Optional[Ranged] = None             # homes: air changes at 50 Pa
    envelope_leakage_l_s_m2_75pa: Optional[Ranged] = None   # offices
    cooling_rating: Optional[Ranged] = None
    cooling_rating_metric: Optional[Literal["SEER", "SEER2", "EER", "EER2", "IEER"]] = None
    heating_rating: Optional[Ranged] = None
    heating_rating_metric: Optional[Literal["HSPF", "HSPF2", "AFUE", "COP"]] = None
    compressor_type: Literal["single", "two_stage", "variable", "unknown"] = "unknown"
    cooling_capacity_w: Optional[float] = None
    heating_cop_47f: Optional[float] = None
    hvac_install_year: Optional[int] = None
    distribution_efficiency: Optional[Ranged] = None
    duct_location: Literal["conditioned", "attic", "garage", "crawlspace", "none", "unknown"] = "unknown"
    outdoor_air_m3_s: Optional[Ranged] = None
    has_economizer: Optional[bool] = None
    economizer_limit_c: Optional[float] = None
    heating_setpoint_c: Optional[Ranged] = None
    cooling_setpoint_c: Optional[Ranged] = None
    heating_setback_c: Optional[float] = None
    cooling_setup_c: Optional[float] = None
    dhw_location: Literal["conditioned", "garage", "outdoor", "unknown"] = "unknown"

class RoofPlane(BaseModel):
    id: str
    polygon_wkt: str                           # map coordinates
    area_m2: float
    tilt_deg: Ranged
    azimuth_deg: float
    usable_area_m2: float
    obstructions: list[VexcelDetection] = []
    obstruction_counts: dict[str, int] = {}    # from Vexcel roof-objects, e.g. {"chimney": 1}; no positions
    ridge_confirmed: bool = False              # False = ridge direction assumed; both hypotheses are in the range
    eave_length_m: Optional[float] = None
    slope_length_m: Optional[float] = None
    geometry_source: Literal["splat", "vexcel_parametric", "assumed"]

class FuelFit(BaseModel):
    """Fit of the model to one fuel's twelve monthly bills (physics 04 MV-03, MV-04)."""
    fuel: Literal["electricity", "gas"]
    nmbe_before: float                         # fraction, simulated minus billed, before calibration
    cv_rmse_before: float                      # fraction
    nmbe_after: float
    cv_rmse_after: float
    passed: bool                               # MV-04: |NMBE| <= 0.05 and CV(RMSE) <= 0.15 (monthly)

class CalibrationSummary(BaseModel):
    """What calibrating to the bills did (physics 04 MV-06). Present only when bills were given."""
    calibrated: bool                           # MV-04 passed for every billed fuel
    fits: list[FuelFit]
    moved: list[str] = []                      # assumption keys changed, each within its stated range
    warnings: list[str] = []                   # e.g. months that disagree, likely unmodelled loads, no billing dates

class BuildingModel(BaseModel):
    schema_version: str = SCHEMA_VERSION
    sid: str
    bedrooms: Optional[int] = None             # homes; drives hot water and occupancy defaults
    north_offset_deg: Ranged                   # azimuth of the model frame's +y axis, degrees clockwise from true
                                               # north, so azimuth_true = azimuth_in_model + north_offset_deg
                                               # (physics ROOF-02). Derived from the georeference quaternion; which
                                               # way that quaternion rotates is [P]: confirm on the golden house
                                               # against the Vexcel footprint before trusting the sign
    north_source: Literal["georeference", "footprint_registration", "assumed"] = "georeference"
    zones: list[Zone]
    surfaces: list[Surface]
    systems: Systems
    roof_planes: list[RoofPlane] = []
    assumptions: list[Assumption]
    flags: list[Flag] = []
    calibration: Optional[CalibrationSummary] = None   # set by calibrate_model; the assumptions are already calibrated

class EnergyUse(BaseModel):
    electricity_kwh: Ranged
    gas_kwh: Ranged
    cost_usd: Ranged
    co2_kg: Ranged                             # kg CO2-equivalent, first year: eGRID total-output rate for
                                               # electricity plus the EPA combustion factor for gas (physics EMI)
    co2_nonbaseload_kg: Optional[Ranged] = None   # the "up to" figure at the eGRID non-baseload rate

class BaselineResult(BaseModel):
    annual: EnergyUse
    end_use_kwh: dict[str, float]              # expected values; keys: heating, cooling, water_heating,
                                               # lighting, plug, appliances
    monthly_electricity_kwh: list[float]       # 12 values, expected
    monthly_gas_kwh: list[float]
    peak_cooling_w: float
    peak_heating_w: float
    calibrated_to_bills: bool = False
    calibration: Optional[CalibrationSummary] = None   # copied from the model; None when no bills were given
    heating_need_kwh: Optional[float] = None   # thermal need before system efficiency
    cooling_need_kwh: Optional[float] = None
    latent_cooling_kwh: float = 0.0
    hourly_path: Optional[str] = None          # cached hourly zone outputs, read by the desk-placement physics
    warnings: list[str] = []                   # sanity checks on the result, e.g. the BEN-03 benchmark band (A31)

MeasureId = Literal[
    "ENV_ATTIC", "ENV_WALL", "ENV_AIRSEAL", "WIN_REPLACE", "WIN_FILM", "WIN_SHADE",
    "ROOF_COOL", "HVAC_HP", "HVAC_RTU", "HVAC_ECON", "HVAC_DUCT", "DHW_HPWH",
    "LGT_LED", "LGT_CTRL", "PLUG_MGMT", "CTRL_TSTAT", "PV_ROOF", "LAYOUT"]

class Incentive(BaseModel):
    name: str
    kind: Literal["upfront_rebate", "rebate_after_install", "tax_credit", "tax_deduction",
                  "performance_payment"]         # only upfront_rebate reduces net_upfront_usd
    amount_usd: Ranged
    status: Literal["verified", "unverified", "expired"]          # of the program itself
    eligibility: Literal["confirmed", "needs_confirmation", "not_eligible"] = "confirmed"   # of this project
    conditions: list[str] = []                 # what must hold, e.g. "placed in service by 2027-12-31"
    citation: str

class FinancingScenario(BaseModel):
    kind: Literal["cash", "cpace"]
    eligible: bool
    financed_usd: float = 0.0
    rate: Optional[float] = None
    term_years: Optional[int] = None
    annual_payment_usd: float = 0.0
    net_cashflow_year1_usd: Ranged             # at base-date prices
    program_sir: Optional[float] = None        # the PACE program's own test (physics ECO-12b): undiscounted
                                               # savings over the term / total cost with financing costs;
                                               # Texas requires >= 1. Not the same as FinancialBreakdown.sir
    notes: list[str] = []

class FinancialBreakdown(BaseModel):
    installed_cost_usd: Ranged
    cost_source: str
    incentives: list[Incentive] = []
    net_upfront_usd: Ranged
    annual_savings_usd: Ranged
    annual_om_change_usd: float = 0.0
    useful_life_years: int
    simple_payback_years: Optional[Ranged] = None
    discounted_payback_years: Optional[float] = None
    npv_usd: Ranged
    npv_sensitivity_usd: Optional[float] = None   # NPV at the 7 percent sensitivity rate (physics ECO-05)
    sir: Optional[float] = None                # discounted savings-to-investment ratio (physics ECO-09)
    irr: Optional[float] = None                # conventional IRR; None when it is not unique
    airr: Optional[float] = None               # adjusted internal rate of return (physics ECO-10)
    discount_rate: float                       # real, not nominal
    electricity_escalation: float              # real, per year
    gas_escalation: float                      # real, per year
    analysis_period_years: int                 # min(useful life, 40)
    financing: list[FinancingScenario]

class Anchor(BaseModel):
    """Where to pin the measure in the 3D tour."""
    room_id: Optional[str] = None
    pano_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    label: str

class PanelPlacement(BaseModel):
    plane_id: str
    polygon_wkt: Optional[str] = None          # None when the layout is a count by area, not drawn positions
    annual_kwh: float
    shading_loss_fraction: float

class SolarDesign(BaseModel):
    system_kw_dc: float
    panel_count: int
    panels: list[PanelPlacement]
    annual_kwh: Ranged
    self_consumption_fraction: Optional[float] = None
    module_w: Optional[float] = None           # rated DC power per module
    dc_ac_ratio: Optional[float] = None
    inverter_kw_ac: Optional[float] = None
    losses_percent: Optional[float] = None     # total system losses applied (physics PV entries)
    degradation_rate: Optional[float] = None   # fraction per year
    electrical: Flag
    structural: Flag

class DeskScore(BaseModel):
    room_id: str
    x: float
    y: float
    daylight: float                            # daylight autonomy at 300 lux: fraction of occupied hours, 0 to 1
    glare_risk: float                          # fraction of occupied hours with glare, 0 to 1
    comfort_ppd: float                         # mean predicted percentage dissatisfied, percent, 5 to 100
    score: float                               # 0 to 1 (physics LCT-03)
    recommended: bool = False
    daylight_factor: Optional[float] = None    # percent
    view_azimuth_deg: Optional[float] = None   # recommended facing direction, clockwise from true north
    direct_sun_hours: Optional[float] = None   # occupied hours per year with the sun in view
    max_dt_pr_k: Optional[float] = None        # worst radiant temperature asymmetry, K
    warnings: list[str] = []

class LayoutResult(BaseModel):
    candidates: list[DeskScore]
    desks_requested: int
    window_source: Optional[Literal["measured", "vision"]] = None
    target_lux: Optional[float] = None
    setpoint_lux: Optional[float] = None
    control_type: Optional[str] = None         # lighting control assumed for the saving (physics LCT-01)
    score_weights: dict[str, float] = {}
    occupied_hours_per_year: Optional[float] = None
    lighting_kwh_saved: Optional[Ranged] = None
    warnings: list[str] = []                   # e.g. "window geometry read from panoramas"

class MeasureResult(BaseModel):
    measure_id: MeasureId
    title: str
    applicable: bool
    not_applicable_reason: Optional[str] = None
    description: str = ""
    params: dict = {}
    savings: Optional[EnergyUse] = None        # annual, against the state it was evaluated on
    finance: Optional[FinancialBreakdown] = None
    flags: list[Flag] = []
    anchors: list[Anchor] = []
    evidence: list[EvidenceRef] = []
    formula_ids: list[str] = []                # physics.md entries used
    solar: Optional[SolarDesign] = None
    layout: Optional[LayoutResult] = None
    value_uplift: Optional["ValueUplift"] = None   # homes with owned rooftop solar only (physics VAL-03)
    warnings: list[str] = []

class PlanItem(BaseModel):
    rank: int
    measure: MeasureResult
    cumulative_upfront_usd: float
    remaining_budget_usd: float

class SkippedItem(BaseModel):
    measure_id: MeasureId
    reason: Literal["over_budget", "role", "feasibility", "no_savings", "not_cost_effective",
                    "already_done", "no_cost_data"]
    detail: str

class ValueUplift(BaseModel):
    """Estimated change in property value from the plan's savings (physics VAL).

    Never added to savings, and never used in NPV, SIR, payback or ranking.
    Commercial and multifamily: capitalised savings, on Plan. Homes: owned rooftop
    solar only, on the PV_ROOF MeasureResult. There is no rent component yet.
    """
    value_usd: Ranged
    method: str                                # physics.md entry id
    cap_rate: Optional[Ranged] = None
    comp_count: int = 0
    notes: list[str] = []

class Plan(BaseModel):
    budget_usd: float
    selected: list[PlanItem]
    financeable: list[MeasureResult]
    skipped: list[SkippedItem]
    total_upfront_usd: Ranged
    total_annual_savings_usd: Ranged
    total_co2_kg: Ranged
    baseline_after: EnergyUse
    value_uplift: Optional[ValueUplift] = None

# ---------- agent and server ----------

Role = Literal["owner_occupier", "landlord", "tenant"]

class UtilityBills(BaseModel):
    electricity_kwh: list[float]               # 12 monthly values
    gas_kwh: Optional[list[float]] = None
    first_month: Optional[str] = None          # "YYYY-MM" of the first bill; None = January, calendar months

class RunRequest(BaseModel):
    sid: str
    budget_usd: float = Field(ge=0)
    role: Role = "owner_occupier"
    bills: Optional[UtilityBills] = None
    overrides: dict[str, Union[float, str, bool]] = {}   # assumption key -> value
    desks_requested: Optional[int] = None
    mode: Optional[Literal["agent", "analysis"]] = None   # "analysis": live data and the analysis door on this request, no agent narration (about 10 s); None: the server default (AGENT_MODE)

class Choice(BaseModel):
    label: str
    value: Union[float, str, bool, None]       # None = "I don't know"

class Question(BaseModel):
    id: str
    assumption_key: str
    prompt: str
    choices: list[Choice]
    impact_note: str

class RunEvent(BaseModel):
    type: Literal["stage_started", "stage_done", "todo", "tool_call", "fallback",
                  "question", "partial_result", "error", "done"]
    stage: Optional[str] = None
    message: str = ""
    payload: dict = {}

class RunResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    run_id: str
    status: Literal["running", "waiting_for_user", "done", "error"]
    request: RunRequest
    property: PropertySummary
    building_model: Optional[BuildingModel] = None
    baseline: Optional[BaselineResult] = None
    measures: list[MeasureResult] = []
    plan: Optional[Plan] = None
    questions: list[Question] = []
    narrative_md: str = ""
    warnings: list[str] = []
    data_source: Optional[Literal["live", "example"]] = None   # what the analysis ran on: live sponsor data, or the
                                                # committed example bundle; a replayed recording keeps the value it was recorded with
    served_by: Optional[Literal["live", "replay", "analysis"]] = None   # how this result reached the client; "analysis" = computed now, no agent

DocType = Literal["retrofit_contract_residential", "retrofit_contract_commercial",
                  "solar_installation_agreement", "bid_package_rfp",
                  "energy_savings_guarantee", "cpace_package"]

class DocumentRequest(BaseModel):
    run_id: str
    doc_type: DocType
    state: Literal["CA", "TX"]
    measure_ids: list[MeasureId]
    fields: dict[str, str] = {}                # user-supplied placeholders, by name

class StatutoryCheck(BaseModel):
    requirement_id: Optional[str] = None       # id in specs/legal/*.md, e.g. "CA-HIC-03"
    requirement: str
    citation: str
    satisfied: bool
    note: Optional[str] = None

class DocumentDraft(BaseModel):
    doc_id: str
    doc_type: DocType
    state: Literal["CA", "TX"]
    markdown: str
    unfilled_placeholders: list[str]
    statutory_checks: list[StatutoryCheck]
    disclaimer: str
