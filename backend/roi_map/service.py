"""What `GET /api/roi-map` serves: the rows `build.py` wrote, read from backend/roi_map/data/."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent / "data"
CITIES = {"la": "Los Angeles County", "houston": "Harris County (Houston)"}


def roi_map(city: str) -> Optional[dict]:
    """The map for `la` or `houston`, or None for an unknown city or when it has not been built."""
    if city not in CITIES:
        return None
    path = DATA / f"{city}.json"
    return json.loads(path.read_text()) if path.is_file() else None
