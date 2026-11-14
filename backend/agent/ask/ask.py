"""Ask rule (G3): SPEC 5.3 step 4 and SPEC 8 rule 3.

`AskSession` holds the questions `sensitivity` returned, hands them out one at a time, stops
after ASK_MAX, and turns each answer into a `set_assumption` call. "I don't know" (value
None) changes nothing, so the range stays. `make_ask_user` is the tool for the auditor: it
pauses the run with langgraph's `interrupt()` and resumes with the user's answer.
"""
from __future__ import annotations

from typing import Callable, Optional, Union

from backend.schema import Question, RunEvent

try:                                # the Analysis lane owns backend/config.py
    from backend.config import ASK_MAX as _CFG_ASK_MAX
except (ImportError, AttributeError):
    _CFG_ASK_MAX = 3
ASK_MAX = _CFG_ASK_MAX

Value = Union[float, str, bool, None]


class AskSession:
    def __init__(self, questions: list[Question], ask_max: int = ASK_MAX):
        self._queue = list(questions)
        self.ask_max = ask_max
        self.asked: list[Question] = []
        self.pending: Optional[Question] = None
        self.answers: dict[str, Value] = {}

    @property
    def status(self) -> str:
        """RunResult.status contribution: waiting_for_user while a question is open."""
        return "waiting_for_user" if self.pending is not None else "running"

    def next_question(self) -> Optional[Question]:
        """The one open question, a new one, or None (empty list, ASK_MAX reached, all asked)."""
        if self.pending is not None:
            return self.pending
        if len(self.asked) >= self.ask_max or not self._queue:
            return None
        self.pending = self._queue.pop(0)
        self.asked.append(self.pending)
        return self.pending

    def event(self, q: Question) -> RunEvent:
        return RunEvent(type="question", stage="ask", message=q.prompt,
                        payload={"question": q.model_dump(mode="json")})

    def answer(self, question_id: str, value: Value,
               set_assumption: Callable[[str, Union[float, str, bool]], object]) -> bool:
        """Close the open question. Returns True when an assumption was set."""
        if self.pending is None or self.pending.id != question_id:
            raise LookupError(f"no open question {question_id}")
        q, self.pending = self.pending, None
        self.answers[q.id] = value
        if value is None:                    # "I don't know": the range stays
            return False
        if not any(c.value == value for c in q.choices):
            raise ValueError(f"{value!r} is not one of the choices of {q.id}")
        set_assumption(q.assumption_key, value)
        return True


def make_ask_user(session: AskSession,
                  set_assumption: Callable[[str, Union[float, str, bool]], object]) -> Callable:
    """The `ask_user` tool. Pauses the run (langgraph interrupt) until the answer arrives;
    returns None without pausing when there is nothing left to ask.
    Resume it with `Command(resume={"value": answer})`."""
    from langgraph.types import interrupt

    def ask_user() -> Value:
        """Ask the user the next open question (only called under SPEC 5.3)."""
        q = session.next_question()
        if q is None:
            return None
        reply = interrupt({"question": q.model_dump(mode="json")})
        # Resume with Command(resume={"value": v}). A bare resume=None breaks langgraph
        # (UnboundLocalError in 1.2.22), and "I don't know" is None.
        value = reply["value"] if isinstance(reply, dict) and "value" in reply else reply
        session.answer(q.id, value, set_assumption)
        return value
    return ask_user
