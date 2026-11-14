"""Door of the legal lane (workplan 3.3).

Wired to the real lane: `backend.legal.engine` (L1) fills the template, the templates
under `templates/` (L2) are the only documents offered, and `backend.legal.checks` (L3)
runs the statutory predicates. Before this, all three functions returned the fixtures in
`specs/examples/` behind the final signatures, so L1, L2 and L3 were dead code while the
agent and `POST /api/runs/{id}/documents` showed a relabelled fixture.

Three rules the stub broke, and why each matters:

- **Only a document with a template is offered.** The stub listed six `DocType`s from a
  hardcoded tuple while one template file existed, so the `counsel` subagent could ask
  for `bid_package_rfp` and be handed the house's draft under that name. `list_templates`
  now reports what is actually loadable, and a request for anything else raises
  `LookupError` rather than inventing a document.
- **Nothing is invented.** A party name, licence number, party address or legal
  description has no binding in the engine (`specs/legal.md` 1.1) and can only come from
  `DocumentRequest.fields`. Everything else becomes a **visible** blank that is also
  listed in `unfilled_placeholders`.
- **The checks are run, not echoed.** `check_document` was `return
  list(draft.statutory_checks)`, which reported whatever the fixture carried - so a
  draft that had never been checked looked checked.

**`stat_` placeholders are blanks today, and the checks fail on them.** There is no
loader for the verbatim statute text in `specs/legal/*.md`, so those names resolve to
blanks and `checks.py` reports the corresponding `CA-R-*` requirements unsatisfied. That
is correct and is exactly what SPEC 15 step 7 asks to show - "the filled terms, **the
blanks**, and the statutory checklist". Do not fill them with paraphrased statute to make
the checklist green; a contract citing invented statutory language is worse than one
showing a blank.

**What is not covered.** L4 to L6 (the commercial, solar, RFP, guarantee and C-PACE
templates, and Texas) do not exist, so the only draftable document is the California
residential retrofit contract. The `office` and `office_houston` examples request
`retrofit_contract_commercial` and `cpace_package`, which are therefore refused - raised
with @yalexie1 on the board, because it narrows SPEC 15 step 7 to the house. L7 adds
predicates for the other documents; until then `check_document` returns `[]` for them,
which means "not checked" and must never be presented as "nothing wrong".
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from backend.legal.checks import checks as _checks
from backend.legal.engine import engine
from backend.schema import (DocType, DocumentDraft, DocumentRequest, PropertyBundle,
                            RunResult, Segment, StatutoryCheck)

_TEMPLATES = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=1)
def _registry() -> dict[tuple[str, str], engine.Template]:
    """Every template on disk, by `(doc_type, state)`.

    Cached because `load_templates` reads and parses every `.md` under `templates/` and
    the door is called once per document in a run. A template added to the tree needs a
    process restart to appear, which is the right trade for a read-only registry.
    """
    return engine.load_templates(_TEMPLATES)


def list_templates(state: Optional[Literal["CA", "TX"]] = None,
                   segment: Optional[Segment] = None) -> list[DocType]:
    """The documents that can actually be drafted for this state and segment.

    `cpace_package` is additionally commercial-only (eligibility itself is decided by
    `cpace_scenario`, not here). The rule is kept even though no C-PACE template exists
    yet, so it is already right when L6 lands.
    """
    offered = engine.list_templates(_registry(), state=state, segment=segment)
    return [t for t in offered if t != "cpace_package" or segment in (None, "commercial")]


def fill_template(request: DocumentRequest, run: RunResult,
                  bundle: Optional[PropertyBundle] = None) -> DocumentDraft:
    """Fill the template for `request`, or raise `LookupError` if there is none.

    `LookupError` and not a fixture: the caller asked for a specific document in a
    specific state, and the honest answer when it does not exist is that it does not
    exist. `list_templates` is how a caller finds out first.
    """
    template = _registry().get((request.doc_type, request.state))
    if template is None:
        raise LookupError(
            f"no template for {request.doc_type} in {request.state}; "
            f"available: {sorted(set(_registry()))}")
    return engine.fill_template(request, run, bundle, template)


def check_document(draft: DocumentDraft) -> list[StatutoryCheck]:
    """Run the statutory predicates over a draft.

    Returns `[]` for a document type L7 has no predicates for. **That is "not checked",
    not "no problems found"**, and a caller showing a checklist must say which it is.
    """
    return _checks.check_document(draft)
