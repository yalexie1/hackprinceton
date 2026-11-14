"""A16 measure engine: applicability by flow, role and feasibility flags; evaluate a measure
against the current state with a simulate function passed in. The plug-in protocol for the
measure packages is documented in `engine.py`."""
from .catalogue import (ALL_ROLES, CATALOGUE, CONSENT_FLAG, OWNER_ROLES,  # noqa: F401
                        CatalogueEntry, flow_of, place_of)
from .engine import (CHECK_REASONS, REGISTRY, SKIP_PARAM, Plugin, Registry, Skip,  # noqa: F401
                     SkipReason, applicability, apply_measure, energy_saved, evaluate,
                     register, skip_reason)
