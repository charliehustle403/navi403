"""Loop tests (build spec §6.4): tool loop drives the broker; budget = stop-and-report."""

from __future__ import annotations

import json

from sqlmodel import Session

from _fakes import FakeModel, text_response, tool_use_response
from navi.contracts import RunContext
from navi.loop import handle_request, run_loop
from navi.seed import seed_defaults


def _ctx(agent_id: str, *, max_cost: float = 0.5) -> RunContext:
    return RunContext(
        run_id="run-1", agent_id=agent_id, route="answer_inline",
        max_cost_per_run=max_cost, scopes=["kb", "web"],
    )


def test_loop_runs_tool_then_answers(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    model = FakeModel([
        tool_use_response("knowledge_base_search", {"query": "naming"}, cost=0.01),
        text_response("Per the KB, role names must encode type, master, and scope.", cost=0.01),
    ])
    result = run_loop(model, session, _ctx(agent.id), "sys", "daily_driver", "how do I name roles?")
    assert not result.truncated
    assert "scope" in result.answer.lower()
    assert result.evidence, "the KB hit's source path should be collected as evidence"
    assert len(model.calls) == 2


def test_loop_budget_stop_and_report(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    model = FakeModel([
        tool_use_response("knowledge_base_search", {"query": "a"}, cost=0.4, tu_id="t1"),
        tool_use_response("knowledge_base_search", {"query": "b"}, cost=0.4, tu_id="t2"),
        text_response("should never be reached", cost=0.4),
    ])
    result = run_loop(model, session, _ctx(agent.id, max_cost=0.5), "sys", "daily_driver", "q")
    assert result.truncated is True
    assert len(model.calls) == 2  # the 3rd model call is prevented by the budget gate


def test_loop_surfaces_denied_tool_to_model(session: Session, offline_settings: object) -> None:
    agent = seed_defaults(session)
    exfil = "look up " + "A" * 60  # egress backstop will deny this web_search
    model = FakeModel([
        tool_use_response("web_search", {"query": exfil}, cost=0.01),
        text_response("That search was blocked, here is what I can say instead.", cost=0.01),
    ])
    result = run_loop(model, session, _ctx(agent.id), "sys", "daily_driver", "q")
    assert not result.truncated
    second_call_messages = json.dumps(model.calls[1][1])
    assert "DENIED" in second_call_messages  # the broker's refusal is fed back to the model


def test_handle_request_clarify_skips_loop(session: Session, offline_settings: object) -> None:
    seed_defaults(session)
    classifier = text_response(json.dumps(
        {"route": "clarify", "confidence": 0.2, "risk": "low",
         "requires_approval": False, "reason": "too vague"}
    ))
    model = FakeModel([classifier])
    result = handle_request("???", model=model, session=session)
    assert result.route == "clarify"
    assert len(model.calls) == 1  # only the classifier ran; no tool loop
