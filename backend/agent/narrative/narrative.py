"""Explain step (G4): `check_narrative` (SPEC 8 rule 1). The agent never does arithmetic:
every number in the narrative must be a value in the structured RunResult, shown at the
precision the text uses. Pure and deterministic."""
from __future__ import annotations

import re
from typing import Iterator

from backend.schema import RunResult

_NUMBER = re.compile(r"(?<![\w.])\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(%?)")
_YEAR = range(1900, 2101)


def _walk(node) -> Iterator[float]:
    """Every number in a JSON-like tree, plus list lengths (counts such as '2 measures')."""
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, (int, float)):
        yield float(node)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        yield float(len(node))
        for v in node:
            yield from _walk(v)


def extract_numbers(text: str) -> list[tuple[str, float, int, bool]]:
    """(as written, value, decimals shown, is_percent) for each number in the text.
    Years (1900 to 2100, no decimals) and markdown heading digits are not quantities."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for m in _NUMBER.finditer(line):
            whole, frac, pct = m.group(1), m.group(2) or "", bool(m.group(3))
            value = float(whole.replace(",", "") + frac)
            if not frac and not pct and "," not in whole and int(whole) in _YEAR:
                continue
            out.append((m.group(0).lstrip("$"), value, len(frac) - 1 if frac else 0, pct))
    return out


def check_narrative(narrative_md: str, result: RunResult) -> list[str]:
    """Mismatches, one message per number. An empty list means every number matches."""
    pool = sorted(set(_walk(result.model_dump(mode="json", exclude={"narrative_md"}))))
    problems = []
    for written, value, decimals, pct in extract_numbers(narrative_md):
        half = 0.5 * 10 ** -decimals
        candidates = [v * 100 for v in pool] if pct else pool
        if not any(abs(c - value) <= half + 1e-9 for c in candidates):
            problems.append(f"{written}: no structured result has this value")
    return problems
