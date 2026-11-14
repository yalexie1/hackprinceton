import json
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from backend.agent.ask import ASK_MAX, AskSession, make_ask_user
from backend.schema import Choice, Question, RunEvent, RunResult

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"
HOUSE = RunResult.model_validate_json((EX / "house" / "run_result.json").read_text())


def q(i, key="k"):
    return Question(id=f"q{i}", assumption_key=f"{key}{i}", prompt="?", impact_note="n",
                    choices=[Choice(label="a", value=1.0), Choice(label="idk", value=None)])


def test_fixture_question_pauses_with_exactly_one_question():
    s = AskSession(HOUSE.questions)
    first = s.next_question()
    assert first.id == HOUSE.questions[0].id and s.status == "waiting_for_user"
    assert s.next_question() is first            # still the same single open question
    ev = s.event(first)
    RunEvent.model_validate(ev.model_dump())
    assert ev.type == "question" and ev.payload["question"]["id"] == first.id
    events = json.loads((EX / "house" / "run_events.json").read_text())
    assert any(e["type"] == "question" for e in events)


def test_value_answer_calls_set_assumption():
    calls = []
    s = AskSession(HOUSE.questions)
    first = s.next_question()
    chosen = next(c.value for c in first.choices if c.value is not None)
    assert s.answer(first.id, chosen, lambda k, v: calls.append((k, v))) is True
    assert calls == [(first.assumption_key, chosen)] and s.status == "running"


def test_dont_know_changes_nothing():
    calls = []
    s = AskSession(HOUSE.questions)
    first = s.next_question()
    assert s.answer(first.id, None, lambda k, v: calls.append((k, v))) is False
    assert calls == [] and s.answers == {first.id: None}


def test_empty_list_never_pauses():
    s = AskSession([])
    assert s.next_question() is None and s.status == "running"


def test_never_more_than_ask_max():
    s = AskSession([q(i) for i in range(10)])
    n = 0
    while (cur := s.next_question()) is not None:
        s.answer(cur.id, None, lambda *a: None)
        n += 1
    assert n == ASK_MAX == 3 and len(s.asked) == 3
    assert len(AskSession([q(i) for i in range(10)], ask_max=1).asked) == 0


def test_bad_answers_rejected():
    s = AskSession([q(1)])
    cur = s.next_question()
    with pytest.raises(LookupError):
        s.answer("other", 1.0, lambda *a: None)
    with pytest.raises(ValueError):
        s.answer(cur.id, 99.0, lambda *a: None)


class State(TypedDict, total=False):
    got: object


def _graph(tool):
    g = StateGraph(State)
    g.add_node("ask", lambda state: {"got": tool()})
    g.add_edge(START, "ask")
    g.add_edge("ask", END)
    return g.compile(checkpointer=InMemorySaver())


@pytest.mark.parametrize("value,expected_calls", [("first-choice", 1), (None, 0)])
def test_interrupt_pause_and_resume(value, expected_calls):
    if value == "first-choice":                         # the example's own first choice, whatever the example asks
        value = next(c.value for c in HOUSE.questions[0].choices if c.value is not None)
    calls = []
    session = AskSession(HOUSE.questions)
    graph = _graph(make_ask_user(session, lambda k, v: calls.append((k, v))))
    cfg = {"configurable": {"thread_id": "t"}}
    out = graph.invoke({}, cfg)
    pending = out["__interrupt__"]
    assert len(pending) == 1 and pending[0].value["question"]["id"] == HOUSE.questions[0].id
    assert session.status == "waiting_for_user"
    graph.invoke(Command(resume={"value": value}), cfg)
    assert len(calls) == expected_calls and session.status == "running"


def test_tool_does_not_pause_when_nothing_to_ask():
    graph = _graph(make_ask_user(AskSession([]), lambda *a: None))
    out = graph.invoke({}, {"configurable": {"thread_id": "t2"}})
    assert "__interrupt__" not in out and out["got"] is None
