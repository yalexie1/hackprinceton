"""S6 Measure LAYOUT and desk placement (A23; SPEC 6.4). Plug-in for the A16 engine; the door
registers it with the point scorer of physics/daylight bound in:

    for mid, (check, change, describe, formula_ids) in layout.measures(score_point).items():
        engine.register(mid, change=change, describe=describe, check=check, formula_ids=formula_ids)
"""
from backend.analysis.layout.measure import (FORMULA_IDS, MEASURES, TITLE, change, check,  # noqa: F401
                                             describe, measures)
from backend.analysis.layout.placement import (GRID_M, MIN_SPACING_M, SCORE_WEIGHTS,  # noqa: F401
                                               WALL_CLEARANCE_M, Candidate, candidate_grid,
                                               desk_score, place_desks)

__all__ = ["FORMULA_IDS", "MEASURES", "TITLE", "change", "check", "describe", "measures",
           "GRID_M", "MIN_SPACING_M", "SCORE_WEIGHTS", "WALL_CLEARANCE_M", "Candidate",
           "candidate_grid", "desk_score", "place_desks"]
