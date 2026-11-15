"""The model client and image reader that switch on real interior vision (A7) for live runs.

Panoramas go to the Anthropic API and nowhere else (CoStar allowed this for the hackathon). Bytes
come from the data layer's cache. Nothing here prints or stores a key, an image or a reading.
"""
from __future__ import annotations

import base64
import os
import re
import threading
from typing import Callable, Optional

from backend import config

# USD per million tokens for config.VISION_MODEL; an estimate for reporting, not billing.
PRICE_IN_PER_MTOK = 1.0
PRICE_OUT_PER_MTOK = 5.0


class Usage:
    """Running totals of what the vision calls used."""

    def __init__(self) -> None:
        self.calls = self.input_tokens = self.output_tokens = 0
        self._lock = threading.Lock()

    def add(self, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self.calls += 1
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * PRICE_IN_PER_MTOK + self.output_tokens * PRICE_OUT_PER_MTOK) / 1e6


def _media_type(b: bytes) -> str:
    return "image/png" if b[:4] == b"\x89PNG" else "image/jpeg"


def make_ask_model(client=None, usage: Optional[Usage] = None, model: str = config.VISION_MODEL) -> Callable:
    """(images, prompt) -> reply text, one Anthropic call per panorama."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    def ask(images: list[bytes], prompt: str) -> str:
        content = [{"type": "image", "source": {"type": "base64", "media_type": _media_type(b),
                                                "data": base64.b64encode(b).decode()}} for b in images]
        content.append({"type": "text", "text": prompt})
        msg = client.messages.create(model=model, max_tokens=2000,
                                     messages=[{"role": "user", "content": content}])
        if usage is not None and getattr(msg, "usage", None) is not None:
            usage.add(msg.usage.input_tokens, msg.usage.output_tokens)
        return "".join(getattr(b, "text", "") for b in msg.content)

    return ask


def vision_available(env=None) -> bool:
    return bool((env or os.environ).get("ANTHROPIC_API_KEY"))


_PANO_PATH = re.compile(r"(?:^|/)(?P<sid>[^/]+)/(?P<mid>defurnished/)?panos/(?P<pano>[^/]+)/face(?P<i>\d)\.jpg$")


def make_get_bytes(data) -> Callable[[str], bytes]:
    """Path -> bytes through the data layer, cache first. A panorama face path goes through
    `data.get_pano_faces(sid, pano_id, defurnished)` when the data layer has it (it fetches on a miss and caches);
    every other path, or a data layer without it, goes through `data.get_asset`."""
    faces: dict[tuple, list[bytes]] = {}

    def get(path: str) -> bytes:
        fetch = getattr(data, "get_pano_faces", None)
        m = _PANO_PATH.search(path)
        if fetch is None or m is None:
            return data.get_asset(path)
        key = (m["sid"], m["pano"], bool(m["mid"]))
        if key not in faces:
            try:
                faces[key] = fetch(m["sid"], m["pano"], bool(m["mid"]))
            except LookupError:
                if not m["mid"]:
                    raise
                # defurnished faces are not fetched: the furnished panorama is the fallback (policy lives here)
                furnished = (m["sid"], m["pano"], False)
                if furnished not in faces:
                    faces[furnished] = fetch(m["sid"], m["pano"], False)
                faces[key] = faces[furnished]
        return faces[key][int(m["i"])]

    return get


def enable_vision(analysis, data, usage: Optional[Usage] = None) -> bool:
    """Switch vision on for the analysis door `analysis`, reading bytes through `data.get_asset`.
    False (and nothing changed) when the door has no `set_vision` or there is no Anthropic key."""
    setter = getattr(analysis, "set_vision", None)
    if setter is None or not vision_available():
        return False
    setter(ask_model=make_ask_model(usage=usage), get_bytes=make_get_bytes(data))
    return True
