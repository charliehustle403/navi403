"""SAP reviewer tests (build spec §6.6, §8): output contract + dispatch + goldens."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import navi.models  # noqa: F401 — register tables
from _fakes import FakeModel, text_response
from navi import prompts
from navi.loop import handle_request
from navi.sap import has_required_sections, missing_sections
from navi.seed import seed_defaults

_GOLDEN_DIR = Path(__file__).parent / "goldens" / "sap"
_GOLDENS = sorted(_GOLDEN_DIR.glob("*.md"))

VALID_SAP_MARKDOWN = """\
### Summary
Needs work — blanket S_TCODE * and BUKRS * break least privilege.

### Findings
| # | Severity | Area | Finding | Recommendation |
|---|----------|------|---------|----------------|
| 1 | High | Auth hygiene | S_TCODE TCD = * grants all txns | Restrict TCD to the AP set |
| 2 | High | Architecture | BUKRS = * on a single role | Master/derived; BUKRS at derived |

### Gaps
- The exact list of intended AP transactions was not provided.

### Quick wins
- Replace S_TCODE * with an explicit transaction list.
- Introduce a derived role per company code.
"""


# --- output contract ----------------------------------------------------------------------


def test_has_required_sections_true() -> None:
    assert has_required_sections(VALID_SAP_MARKDOWN)
    assert missing_sections(VALID_SAP_MARKDOWN) == []


def test_missing_sections_reported() -> None:
    incomplete = "### Summary\nsound\n\n### Findings\n| # | ... |"
    missing = missing_sections(incomplete)
    assert "### Gaps" in missing and "### Quick wins" in missing


def test_inline_headers_do_not_falsely_pass() -> None:
    # all four header strings appear, but only inline in one prose line — not real sections
    prose = "I considered ### Summary, ### Findings, ### Gaps, and ### Quick wins inline."
    assert not has_required_sections(prose)
    assert len(missing_sections(prose)) == 4


# --- dispatch uses the §8 prompt on deep_reasoning ----------------------------------------


def test_sap_dispatch_uses_section8_prompt(session: Session, offline_settings: object) -> None:
    seed_defaults(session)
    model = FakeModel([text_response(VALID_SAP_MARKDOWN)])
    text = "Please review this SAP PFCG single role design: S_TCODE = *"
    result = handle_request(text, model=model, session=session)

    assert result.route == "sap_review"
    assert result.answer == VALID_SAP_MARKDOWN
    assert has_required_sections(result.answer)
    # the deterministic pre-check short-circuits routing, so the only model call is the review
    assert len(model.calls) == 1
    profile, _messages, _tools, system = model.calls[0]
    assert profile == "deep_reasoning"
    assert system == prompts.SAP_REVIEW


# --- goldens: each fixture routes to sap_review and yields contract-valid markdown ---------


@pytest.mark.parametrize("golden", _GOLDENS, ids=[p.stem for p in _GOLDENS])
def test_golden_routes_to_sap_review(
    golden: Path, session: Session, offline_settings: object
) -> None:
    seed_defaults(session)
    concept = golden.read_text(encoding="utf-8")
    text = f"Please review this SAP role design:\n\n{concept}"
    model = FakeModel([text_response(VALID_SAP_MARKDOWN)])
    result = handle_request(text, model=model, session=session)
    assert result.route == "sap_review"
    assert has_required_sections(result.answer)


def test_goldens_exist() -> None:
    assert len(_GOLDENS) >= 10, "build spec §10 requires >=10 SAP-review goldens"


# --- live smoke test (opt-in; real Opus call) ---------------------------------------------


@pytest.mark.skipif(not os.getenv("NAVI_LIVE_TESTS"), reason="set NAVI_LIVE_TESTS=1 to run live")
def test_live_sap_review_structure() -> None:
    from navi.model_client import ModelClient

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed_defaults(s)
        concept = (_GOLDEN_DIR / "blanket_stcode.md").read_text(encoding="utf-8")
        result = handle_request(
            f"Please review this SAP role design:\n\n{concept}",
            model=ModelClient(),
            session=s,
        )
    assert result.route == "sap_review"
    assert has_required_sections(result.answer), result.answer
