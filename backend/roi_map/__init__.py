"""ROI map (issue 395): estimated rooftop-solar payback per zip code, LA County and Harris County.

An estimate for a typical home, not an audit of any building. See `build.py` for the inputs and `service.py`
for what the route serves."""
from backend.roi_map.service import CITIES, roi_map

__all__ = ["CITIES", "roi_map"]
