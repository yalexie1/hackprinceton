"""The proposed ask-the-user questions must be valid Question objects.

They are a proposal from the Data lane for whoever owns backend/analysis/api.py
(`sensitivity()` returns `list[Question]`). Keeping them schema-valid here means
adopting them is a copy, not a rewrite.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.schema import Question

PATH = Path(__file__).resolve().parents[1] / "proposed_questions.json"
QUESTIONS = [Question.model_validate(q) for q in json.loads(PATH.read_text())]


def test_every_proposed_question_validates_against_the_contract():
    assert len(QUESTIONS) >= 5


def test_every_question_offers_an_i_dont_know_choice():
    # A question with no escape hatch forces a guess, and a guessed answer is
    # worse than no answer because it arrives with false confidence.
    for q in QUESTIONS:
        assert any(c.value is None for c in q.choices), q.id


def test_ids_and_assumption_keys_are_unique():
    assert len({q.id for q in QUESTIONS}) == len(QUESTIONS)
    assert len({q.assumption_key for q in QUESTIONS}) == len(QUESTIONS)


def test_the_two_biggest_drivers_of_predicted_electricity_are_asked_about():
    # Plug (median 41% of predicted electricity) and lighting (32%) dominate the
    # estimate, so an ask rule that skips them is asking about the wrong things.
    keys = {q.assumption_key for q in QUESTIONS}
    assert "plug.ppd" in keys
    assert "lighting.lpd" in keys


def test_impact_notes_explain_the_consequence_not_the_parameter():
    for q in QUESTIONS:
        assert len(q.impact_note) > 80, q.id
        assert "%" in q.impact_note or "twice" in q.impact_note or "times" in q.impact_note, q.id


def test_prompts_are_answerable_without_knowing_the_model():
    # No prompt should name an internal parameter: a building owner knows what
    # lights they have, not what their lighting power density is.
    jargon = ("lpd", "ppd", "w/m2", "u-value", "shgc", "ach50", "power density")
    for q in QUESTIONS:
        assert not any(j in q.prompt.lower() for j in jargon), q.id
