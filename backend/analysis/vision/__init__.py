"""A7 and A8 S3 See, interior: glazing, HVAC, water heater, lighting and feasibility cues read from
panoramas (workplan 4.2).

The model call and the image bytes are passed in; nothing here opens a network connection on its
own. Imported only by ``backend/analysis/api.py``. A8 (``feasibility.py``: wall material, outlets,
main panel) rides on the same per-panorama call and fills ``VisionResult.flags``.
"""
from .feasibility import feasibility_from_readings
from .interior import (PROMPT, REPLY_SCHEMA, AskModel, GetBytes, PanoReading, VisionResult,
                       assumptions_from_readings, build_prompt, observe_interior, parse_reply,
                       read_interior, select_panos)

__all__ = ["feasibility_from_readings", "PROMPT", "REPLY_SCHEMA", "AskModel", "GetBytes", "PanoReading", "VisionResult",
           "assumptions_from_readings", "build_prompt", "observe_interior", "parse_reply",
           "read_interior", "select_panos"]
