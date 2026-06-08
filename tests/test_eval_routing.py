"""Eval suite — routing (build spec §10): right route/dispatch for the input.

Graded on the dispatched route. SAP/dispatch-policy cases are deterministic (no model);
classifier cases use a FakeModel returning the decision so the route() integration is exercised.
"""

from __future__ import annotations

import json

import pytest

from _fakes import FakeModel, text_response
from navi.router import dispatch_route, route


def _decision(route_: str, confidence: float, risk: str = "low") -> str:
    return json.dumps(
        {"route": route_, "confidence": confidence, "risk": risk,
         "requires_approval": False, "reason": "eval"}
    )


# (label, text, classifier_json | None, expected_dispatched)
_AI = _decision("answer_inline", 0.95)
_CASES = [
    ("sap_explicit", "/sap-review here is my role", None, "sap_review"),
    ("sap_keywords", "Please review this SAP PFCG derived role design", None, "sap_review"),
    ("sap_stcode", "assess the S_TCODE auth object in this role", None, "sap_review"),
    ("sap_composite", "review the SAP composite role naming", None, "sap_review"),
    ("inline_fact", "what is the capital of France", _AI, "answer_inline"),
    ("inline_explain", "explain how recursion works", _AI, "answer_inline"),
    ("research_news", "find the latest news on AI chips", _decision("research", 0.9), "research"),
    ("research_web", "search the web for SAP licensing", _decision("research", 0.85), "research"),
    ("low_conf_clarifies", "ummm something", _decision("answer_inline", 0.4), "clarify"),
    ("mid_conf_clarifies", "do the thing", _decision("research", 0.55), "clarify"),
    ("high_risk_refuses", "do harm", _decision("answer_inline", 0.9, "high"), "refuse"),
    ("classifier_clarify", "?", _decision("clarify", 0.2), "clarify"),
]


@pytest.mark.parametrize("label,text,classifier,expected", _CASES, ids=[c[0] for c in _CASES])
def test_routing(label: str, text: str, classifier: str | None, expected: str) -> None:
    model = FakeModel([] if classifier is None else [text_response(classifier)])
    decision = route(model, text)
    got = dispatch_route(decision)
    assert got == expected, f"{label}: routed to {got}"
    if classifier is None:
        assert model.calls == []  # deterministic pre-check did not call the model
