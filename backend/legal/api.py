"""Door of the legal lane (workplan 3.3).

L0 stub: the three door functions return the fixtures in specs/examples/ behind the final
signatures. Real drafting replaces the bodies later; the signatures stay.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from backend.schema import (DocType, DocumentDraft, DocumentRequest, PropertyBundle,
                            RunResult, Segment, StatutoryCheck)

_EXAMPLES = Path(__file__).resolve().parents[2] / "specs" / "examples"

_ALL: tuple[DocType, ...] = ("retrofit_contract_residential", "retrofit_contract_commercial",
                             "solar_installation_agreement", "bid_package_rfp",
                             "energy_savings_guarantee", "cpace_package")


def list_templates(state: Literal["CA", "TX"] | None = None,
                   segment: Segment | None = None) -> list[DocType]:
    """cpace_package is listed only for segment "commercial" (eligibility is decided by
    cpace_scenario). The stub lists every type for both states."""
    return [t for t in _ALL if t != "cpace_package" or segment in (None, "commercial")]


def fill_template(request: DocumentRequest, run: RunResult,
                  bundle: PropertyBundle | None = None) -> DocumentDraft:
    """Stub: the fixture draft, relabelled with the request's type and state. A real
    implementation never invents a party, licence number or legal description."""
    flavor = "office" if run.property.segment == "commercial" else "house"
    draft = DocumentDraft.model_validate(
        json.loads((_EXAMPLES / flavor / "document_draft.json").read_text()))
    draft.doc_type = request.doc_type
    draft.state = request.state
    draft.doc_id = f"doc_{run.run_id}_{request.doc_type}"
    return draft


def check_document(draft: DocumentDraft) -> list[StatutoryCheck]:
    return list(draft.statutory_checks)
