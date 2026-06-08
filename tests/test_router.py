"""Router tests (build spec §6.5): deterministic pre-check, classifier, dispatch policy."""

from __future__ import annotations

import json

from _fakes import FakeModel, text_response
from navi.contracts import RouteDecision
from navi.router import dispatch_route, route


def test_sap_precheck_explicit_command() -> None:
    decision = route(FakeModel([]), "/sap-review here is my role concept")
    assert decision.route == "sap_review"


def test_sap_precheck_keywords() -> None:
    decision = route(
        FakeModel([]), "Can you review this SAP PFCG derived role design for SoD problems?"
    )
    assert decision.route == "sap_review"


def test_classifier_returns_structured_route() -> None:
    payload = json.dumps(
        {"route": "research", "confidence": 0.9, "risk": "low",
         "requires_approval": False, "reason": "needs current info"}
    )
    decision = route(FakeModel([text_response(payload)]), "what is the latest on quantum chips")
    assert decision.route == "research"
    assert decision.confidence == 0.9


def test_classifier_parse_failure_defaults_to_clarify() -> None:
    decision = route(FakeModel([text_response("sorry, not JSON")]), "mmm")
    assert decision.route == "clarify"


def test_dispatch_low_confidence_clarifies() -> None:
    d = RouteDecision(route="answer_inline", confidence=0.3, risk="low", reason="")
    assert dispatch_route(d) == "clarify"


def test_dispatch_high_risk_refuses() -> None:
    d = RouteDecision(route="answer_inline", confidence=0.95, risk="high", reason="")
    assert dispatch_route(d) == "refuse"


def test_dispatch_passes_through_confident_low_risk() -> None:
    d = RouteDecision(route="research", confidence=0.9, risk="low", reason="")
    assert dispatch_route(d) == "research"
