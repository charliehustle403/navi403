"""Request router (build spec §6.5) — hybrid: deterministic pre-check, then a cheap classifier.

Dispatch policy is **code, not the model's mood**: the thresholds in ``dispatch_route`` override
whatever route the model returned (defense in depth).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from navi.contracts import RouteDecision
from navi.model_client import Completer
from navi.prompts import CLASSIFIER

if TYPE_CHECKING:
    from navi.trace import RunRecorder

logger = logging.getLogger(__name__)

CONFIDENCE_FLOOR = 0.6

_SAP_KEYWORDS = (
    "sap", "pfcg", "s/4hana", "s4hana", "authorization object", "auth object", "derived role",
    "composite role", "single role", "s_tcode", "role design", "segregation of duties",
    "fiori catalog", "su24",
)
_REVIEW_WORDS = ("review", "assess", "check", "design", "sound", "audit", "evaluate")


def _looks_like_sap_review(text: str) -> bool:
    """Cheap deterministic pre-check for SAP role-review requests (spec §6.4)."""
    low = text.lower()
    if low.strip().startswith("/sap-review"):
        return True
    has_sap = any(k in low for k in _SAP_KEYWORDS)
    has_review = any(w in low for w in _REVIEW_WORDS)
    return has_sap and has_review


def _extract_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in classifier output")
    parsed: dict[str, Any] = json.loads(text[start : end + 1])
    return parsed


def _classify(
    model: Completer, text: str, recorder: RunRecorder | None = None
) -> RouteDecision:
    """Run the cheap_triage classifier; any failure defaults safely to clarify."""
    try:
        resp = model.complete("cheap_triage", [{"role": "user", "content": text}], None, CLASSIFIER)
        if recorder is not None:
            recorder.model_call(resp)  # fold the routing cost into the run
        return RouteDecision(**_extract_json(resp.text))
    except Exception:
        logger.exception("router classification failed; defaulting to clarify")
        return RouteDecision(
            route="clarify", confidence=0.0, risk="low", reason="classifier parse failure"
        )


def route(model: Completer, text: str, recorder: RunRecorder | None = None) -> RouteDecision:
    """Decide the route: deterministic SAP pre-check first, else the cheap classifier."""
    if _looks_like_sap_review(text):
        return RouteDecision(
            route="sap_review", confidence=0.95, risk="low", reason="deterministic SAP pre-check"
        )
    return _classify(model, text, recorder)


def dispatch_route(decision: RouteDecision) -> str:
    """Map a decision to the dispatched route. Code overrides the model (spec §6.5)."""
    if decision.confidence < CONFIDENCE_FLOOR:
        return "clarify"
    if decision.risk == "high":
        return "refuse"
    return decision.route
