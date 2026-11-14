"""Explain step (G4): `check_narrative` (SPEC 8 rule 1). The agent never does arithmetic:
every number in the narrative must be a value in the structured RunResult, shown at the
precision the text uses. Callers may also pass the PropertyBundle and the BuildingModel, and
the numbers in the property address (street number, ZIP) are always accepted: those are
data the agent reads, not figures it computes. Pure and deterministic."""
from __future__ import annotations

import re
from typing import Iterator, Optional

from backend.schema import BuildingModel, PropertyBundle, RunResult

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


_TEXT_KEYS = {"warnings", "detail", "not_applicable_reason", "note"}


def _text_numbers(node, in_text: bool = False) -> Iterator[float]:
    """Numbers written inside the result's own explanatory text (a warning, a skip reason): a report that quotes
    a warning verbatim quotes those numbers too, and they are the result's, not the writer's."""
    if isinstance(node, str):
        if in_text:
            for m in _NUMBER.finditer(node):
                whole, frac = m.group(1), m.group(2) or ""
                yield float(whole.replace(",", "") + frac)
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _text_numbers(v, in_text or k in _TEXT_KEYS)
    elif isinstance(node, list):
        for v in node:
            yield from _text_numbers(v, in_text)


def _address_numbers(*addresses: Optional[str]) -> Iterator[float]:
    for text in addresses:
        for m in re.finditer(r"\d+", text or ""):
            yield float(m.group(0))


def check_narrative(narrative_md: str, result: RunResult,
                    bundle: Optional[PropertyBundle] = None,
                    model: Optional[BuildingModel] = None) -> list[str]:
    """Mismatches, one message per number. An empty list means every number matches."""
    sources = [result.model_dump(mode="json", exclude={"narrative_md"})]
    if bundle is not None:
        sources.append(bundle.model_dump(mode="json"))
    if model is not None:
        sources.append(model.model_dump(mode="json"))
    values = {v for src in sources for v in _walk(src)}
    pool = sorted(values | {abs(v) for v in values}        # a loss is written without its sign: "-$496", "a loss of 496"
                  | {v for src in sources for v in _text_numbers(src)}
                  | set(_address_numbers(result.property.address,
                                         bundle.summary.address if bundle else None)))
    problems = []
    for written, value, decimals, pct in extract_numbers(narrative_md):
        half = 0.5 * 10 ** -decimals
        candidates = [v * 100 for v in pool] if pct else pool
        if not any(abs(c - value) <= half + 1e-9 for c in candidates):
            problems.append(f"{written}: no structured result has this value")
    return problems


def remove_unsupported(narrative_md: str, result: RunResult, bundle: Optional[PropertyBundle] = None,
                       model: Optional[BuildingModel] = None) -> tuple[str, list[str]]:
    """The narrative without the lines that state a number no result holds, and those lines. The
    last resort when the agent has been asked to correct its text and has not."""
    kept, dropped = [], []
    for line in narrative_md.splitlines():
        (dropped if line.strip() and check_narrative(line, result, bundle, model) else kept).append(line)
    return "\n".join(kept), dropped
