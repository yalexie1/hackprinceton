"""S6 Measures ENV_WALL, WIN_REPLACE, WIN_FILM, WIN_SHADE (A20). Reached through
backend.analysis.api, which registers each with the A16 engine:

    for mid, (check, change, describe, formula_ids) in walls_windows.MEASURES.items():
        engine.register(mid, change=change, describe=describe, check=check, formula_ids=formula_ids)
"""
from backend.analysis.measures.walls_windows.walls import (FORMULA_IDS as WALL_FORMULA_IDS,
                                                           wall_change, wall_check, wall_describe)
from backend.analysis.measures.walls_windows.windows import (
    FILM_FORMULA_IDS, REPLACE_FORMULA_IDS, SHADE_FORMULA_IDS, film_change, film_check, film_describe,
    replace_change, replace_check, replace_describe, shade_change, shade_check, shade_describe,
    shade_factor)

# MeasureId -> (check, change, describe, formula_ids)
MEASURES = {
    "ENV_WALL": (wall_check, wall_change, wall_describe, WALL_FORMULA_IDS),
    "WIN_REPLACE": (replace_check, replace_change, replace_describe, REPLACE_FORMULA_IDS),
    "WIN_FILM": (film_check, film_change, film_describe, FILM_FORMULA_IDS),
    "WIN_SHADE": (shade_check, shade_change, shade_describe, SHADE_FORMULA_IDS),
}

__all__ = ["MEASURES", "film_change", "film_check", "film_describe", "replace_change", "replace_check",
           "replace_describe", "shade_change", "shade_check", "shade_describe", "shade_factor",
           "wall_change", "wall_check", "wall_describe"]
