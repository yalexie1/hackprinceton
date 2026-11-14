"""L9: the document structures of specs/legal.md. Every DocType has one, every requirement id the
outlines cite exists in a state file, and every placeholder of Part C names where it comes from."""
import re
from pathlib import Path
from typing import get_args

from backend import schema
from backend.schema import DocType

SPECS = Path(__file__).resolve().parents[3] / "specs"
LEGAL = (SPECS / "legal.md").read_text()
PART_C = LEGAL[LEGAL.index("# Part C."):]
ID = re.compile(r"\b((?:CA|TX)-[A-Z]+-[0-9A-Za-z]+)\b")
STATE_IDS = {i for f in ("california.md", "texas.md") for i in ID.findall((SPECS / "legal" / f).read_text())}
CLASSES = {n for n in dir(schema) if n[:1].isupper()}


def test_every_doctype_has_a_document_structure():
    table = LEGAL[LEGAL.index("## 2. Documents"):LEGAL.index("# Part A.")]
    for doc_type in get_args(DocType):
        row = next((l for l in table.splitlines() if f"`{doc_type}`" in l), None)
        assert row is not None, doc_type
        assert "written" in row or "outline" in row, f"{doc_type} has no structure: {row}"
    # the five documents outlined in Part C each have a section of their own
    for heading in ("## 16. Document 2", "## 17. Document 3", "## 18. Document 4", "## 19. Document 5",
                    "## 20. Document 6"):
        assert heading in PART_C, heading


def test_every_requirement_id_the_outlines_cite_exists_in_a_state_file():
    cited = set(ID.findall(PART_C))
    assert len(cited) > 100
    assert not sorted(i for i in cited if i not in STATE_IDS)


def test_each_outline_has_the_same_parts():
    sections = re.split(r"\n## (?=\d+\. Document)", PART_C)[1:]
    assert len(sections) == 5
    for body in sections:
        title = body.splitlines()[0]
        for part in ("**Purpose.**", "**When it applies.**", "**Outline.**", "**Conditional blocks.**",
                     "**New placeholders.**", "**Statutory checks.**", "**Open items.**"):
            assert part in body or (part == "**New placeholders.**" and "Placeholder" in body), (title, part)


def test_every_outline_clause_row_carries_a_requirement_id_or_says_none():
    for table in re.findall(r"\| § \| (?:Clause|Section) .*?\n((?:\|.*\n)+)", PART_C):
        for row in table.splitlines()[1:]:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) < 4 or not cells[0].rstrip(".").isdigit():
                continue
            ids = cells[2] + " " + cells[3]
            assert ID.search(ids) or "none" in ids.lower() or cells[2] == cells[3] == "", row[:90]


def test_every_part_c_placeholder_names_its_source():
    rows = 0
    for table in re.findall(r"\| Placeholder \| Source \|.*?\n((?:\|.*\n)+)", PART_C):
        for row in table.splitlines()[1:]:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) < 4 or set(cells[0]) <= {"-", " "}:
                continue
            rows += 1
            source = cells[1]
            roots = {t.split(".")[0].split("[")[0] for t in re.findall(r"`([^`]+)`", source)}
            ok = re.search(r"\b(user|gen|stat)\b", source) or roots & CLASSES
            assert ok, f"{cells[0]}: source {source!r} is neither user, gen, stat nor a SPEC 9 type"
    assert rows > 40


def test_contract_types_the_outlines_name_exist():
    for name in ("SolarDesign", "FinancingScenario", "Tariff", "Plan", "MeasureResult", "FinancialBreakdown",
                 "PropertySummary", "RunRequest", "DocumentRequest"):
        assert name in PART_C and hasattr(schema, name), name
