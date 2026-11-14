"""A7 S3 See, interior: glazing, HVAC, water heater and lighting read from panoramas (workplan 4.2).

The model call and the image bytes are passed in; nothing here opens a network connection on its
own. Imported only by ``backend/analysis/api.py``. A8 (feasibility cues) is built later in this
folder and fills ``VisionResult.flags``.
"""
from .interior import (PROMPT, REPLY_SCHEMA, AskModel, GetBytes, PanoReading, VisionResult,
                       assumptions_from_readings, build_prompt, observe_interior, parse_reply,
                       read_interior, select_panos)

__all__ = ["PROMPT", "REPLY_SCHEMA", "AskModel", "GetBytes", "PanoReading", "VisionResult",
           "assumptions_from_readings", "build_prompt", "observe_interior", "parse_reply",
           "read_interior", "select_panos"]
