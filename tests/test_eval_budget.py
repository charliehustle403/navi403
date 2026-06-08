"""Eval suite — budget limit (build spec §10): runaway loop stops and reports a partial result."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from _fakes import FakeModel, tool_use_response
from navi.contracts import RunContext
from navi.loop import run_loop
from navi.seed import seed_defaults

# (label, max_cost_per_run, per_call_cost) — costs accumulate until the budget gate fires
_SCENARIOS = [
    ("half_dollar", 0.50, 0.30),
    ("dime", 0.10, 0.06),
    ("two_bits", 0.20, 0.15),
    ("one_dollar", 1.00, 0.60),
    ("nickel", 0.05, 0.03),
]


@pytest.mark.parametrize("label,max_cost,call_cost", _SCENARIOS, ids=[s[0] for s in _SCENARIOS])
def test_budget_stop_and_report(
    label: str, max_cost: float, call_cost: float, session: Session, offline_settings: object
) -> None:
    agent = seed_defaults(session)
    # 8 tool_use turns available; the per-run budget should stop the loop well before the cap
    responses = [
        tool_use_response("knowledge_base_search", {"query": "q"}, cost=call_cost, tu_id=f"t{i}")
        for i in range(8)
    ]
    model = FakeModel(responses)
    ctx = RunContext(
        run_id="r", agent_id=agent.id, route="answer_inline",
        max_cost_per_run=max_cost, scopes=["kb", "web"],
    )
    result = run_loop(model, session, ctx, "sys", "daily_driver", "q")
    assert result.truncated is True, f"{label} should truncate on budget"
    assert ctx.cost_so_far_usd >= max_cost
    assert len(model.calls) < 8  # stopped by budget, not by the iteration cap
