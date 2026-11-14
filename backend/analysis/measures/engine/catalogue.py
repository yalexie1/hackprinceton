"""SPEC 6.2 measure library as data: which flow offers each measure and which role may do it.

Constants local to this package (workplan 2.6); `backend/config.py` holds none of these.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from backend.schema import MeasureId, PropertySummary, Role

Flow = Literal["home", "office"]

ALL_ROLES: frozenset[str] = frozenset(get_args(Role))     # owner_occupier, landlord, tenant
OWNER_ROLES: frozenset[str] = frozenset({"owner_occupier", "landlord"})   # SPEC 6.2 "owner"

# Feasibility flag that carries the owner's consent for a tenant (office_houston fixture).
CONSENT_FLAG = "lease.alteration_consent"


@dataclass(frozen=True)
class CatalogueEntry:
    measure_id: str
    title: str
    flows: frozenset[str]              # "home", "office"
    roles: frozenset[str]              # roles that may do it outright
    consent_roles: frozenset[str]      # roles that may do it only with the owner's consent
    modules: tuple[str, ...]           # SPEC 6.2 "Physics modules", for reference
    blocked_by: tuple[str, ...] = ()   # model flag keys that, when `blocked`, make it not applicable


def _e(mid, title, home, office, who, modules, blocked_by=()):
    roles = {"owner": OWNER_ROLES, "all": ALL_ROLES, "owner, tenant": ALL_ROLES,
             "owner, tenant with consent": OWNER_ROLES}[who]
    consent = frozenset({"tenant"}) if who == "owner, tenant with consent" else frozenset()
    flows = frozenset(f for f, on in (("home", home), ("office", office)) if on)
    return CatalogueEntry(mid, title, flows, frozenset(roles), consent, tuple(modules), tuple(blocked_by))


# SPEC 6.2 table, row by row. `blocked_by` defaults are the flags the fixtures and SPEC 6.3
# step 7 name; a plug-in registration may replace them.
CATALOGUE: dict[str, CatalogueEntry] = {e.measure_id: e for e in (
    _e("ENV_ATTIC", "Attic or roof insulation", 1, 1, "owner", ("envelope", "zone model")),
    _e("ENV_WALL", "Wall insulation", 1, 0, "owner", ("envelope", "zone model")),
    _e("ENV_AIRSEAL", "Air sealing", 1, 1, "owner, tenant with consent", ("infiltration",)),
    _e("WIN_REPLACE", "Window replacement", 1, 1, "owner", ("envelope", "solar gain")),
    _e("WIN_FILM", "Solar control film", 1, 1, "owner, tenant with consent", ("solar gain",)),
    _e("WIN_SHADE", "Exterior or interior shading", 1, 1, "all", ("solar gain",)),
    _e("ROOF_COOL", "Cool roof coating or membrane", 1, 1, "owner", ("envelope", "sol-air")),
    _e("HVAC_HP", "Heat pump replacing AC and furnace", 1, 0, "owner", ("HVAC",)),
    _e("HVAC_RTU", "High-efficiency rooftop unit", 0, 1, "owner", ("HVAC",)),
    _e("HVAC_ECON", "Economizer and controls", 0, 1, "owner", ("ventilation", "HVAC")),
    _e("HVAC_DUCT", "Duct sealing", 1, 0, "owner", ("HVAC",)),
    _e("DHW_HPWH", "Heat pump water heater", 1, 0, "owner", ("water heating",), ("dhw.space",)),
    _e("LGT_LED", "LED retrofit", 1, 1, "all", ("lighting", "HVAC interaction")),
    _e("LGT_CTRL", "Occupancy and daylight controls", 0, 1, "owner, tenant", ("lighting", "daylight")),
    _e("PLUG_MGMT", "Plug load management", 0, 1, "all", ("plug loads",)),
    _e("CTRL_TSTAT", "Smart thermostat and setback", 1, 1, "all", ("zone model",)),
    _e("PV_ROOF", "Rooftop solar", 1, 1, "owner", ("solar pipeline",),
       ("roof.structure", "electrical.service")),
    _e("LAYOUT", "Desk or furniture placement", 1, 1, "all", ("daylight", "glare", "comfort")),
)}

assert set(CATALOGUE) == set(get_args(MeasureId)), "catalogue out of step with the contract"

_HOME_USES = {"single_family", "multifamily_unit"}
_PLACE = {"single_family": "a single-family home", "multifamily_unit": "a home in a multifamily building",
          "office": "an office property", "retail": "a retail property", "other": "a commercial property",
          "unknown": "a property of unknown use"}


def flow_of(summary: PropertySummary) -> Flow:
    """Home flow for single-family and multifamily units, office flow for offices; anything
    else falls back on the segment (residential = home, commercial = office)."""
    if summary.use_type in _HOME_USES:
        return "home"
    if summary.use_type == "office":
        return "office"
    return "home" if summary.segment == "residential" else "office"


def place_of(summary: PropertySummary) -> str:
    return _PLACE.get(summary.use_type, "this property")
