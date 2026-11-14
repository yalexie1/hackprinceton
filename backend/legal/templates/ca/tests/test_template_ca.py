import re
from pathlib import Path

PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")


def placeholders_in(text):
    return list(dict.fromkeys(PLACEHOLDER.findall(text)))


def header(key):
    m = re.search(r"<!--\s*" + key + r":\s*(.*?)\s*-->", TEXT)
    return m.group(1) if m else None


ROOT = Path(__file__).resolve().parents[5]
SPEC = (ROOT / "specs" / "legal.md").read_text().split("\n")
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "retrofit_contract_residential.md"
TEXT = TEMPLATE_PATH.read_text()


def _section(start_prefix, end_prefix):
    a = next(i for i, l in enumerate(SPEC) if l.startswith(start_prefix))
    b = next(i for i, l in enumerate(SPEC) if i > a and l.startswith(end_prefix))
    return SPEC[a:b]


def _first_cell_names(lines):
    names = set()
    for l in lines:
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].startswith("`"):
            names.update(re.findall(r"`([a-z0-9_]+)`", cells[0]))
    return names


def test_header():
    assert header("doc").split("/")[:2] == ["retrofit_contract_residential ", " CA "]
    assert header("segments") == "residential"


def test_every_placeholder_is_in_the_legal_spec_tables():
    known = (_first_cell_names(_section("## 5. Placeholder table", "## 6."))
             | _first_cell_names(_section("### 4.A", "## 5."))
             | {"progress_payment_table", "schedule_a_rows"})
    unknown = [p for p in placeholders_in(TEXT) if p not in known]
    assert unknown == []


def test_optional_names_are_placeholders_of_the_template():
    optional = {n.strip() for n in header("optional").split(",")}
    assert optional <= set(placeholders_in(TEXT))


def test_every_required_term_id_has_a_clause_carrying_it():
    section6 = _section("## 6. Statutory checks", "## 7.")
    needed = set()
    for l in section6:
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0].startswith("CA-R-"):
            needed.update(re.findall(r"CA-[A-Z]+-\d+[a-z]?", cells[4]))
    assert needed, "no ids found in legal.md section 6"
    carried = set()
    for m in re.finditer(r"<!--\s*clause:(.*?)-->", TEXT, re.S):
        carried.update(re.findall(r"CA-[A-Z]+-\d+[a-z]?", m.group(1)))
    assert needed - carried == set()


def test_notice_block_and_not_a_copied_form():
    assert TEXT.count("{{disclaimer}}") == 2
    assert "our own wording" in TEXT.lower()
