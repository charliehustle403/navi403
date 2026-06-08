"""Provenance-gated memory service (build spec §6.7, §4 master doc Part IV).

The gate is the first-write boundary for long-term memory and is enforced, not optional:

- **Untrusted source -> quarantined.** A "fact" from tool output / a document is stored only in
  ``memory_candidates`` (as a hash, status ``pending``) and NEVER written to ``memories`` — that
  is the indirect-injection -> memory-poisoning chain, broken.
- **Trusted but sensitive -> rejected.** PII / credentials / anything classified sensitive is
  rejected (recorded as a hashed, ``rejected`` candidate), never stored as a plain memory.
- **Trusted and not sensitive -> accepted.** Written to ``memories`` with full provenance and
  ``may_influence_actions = False`` (low-trust/unconfirmed memories may not drive actions).

Gate-only in the MVP: nothing in the read-only loop produces candidates automatically; ``consider``
is exercised directly. A live ingestion path is post-MVP.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from sqlmodel import Session

from navi.contracts import MemoryCandidate
from navi.models import Memory
from navi.models import MemoryCandidate as MemoryCandidateRow

MemoryOutcome = Literal["accepted", "quarantined", "rejected"]

_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # email
    re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),  # SSN-ish
    re.compile(r"\b(?:\d[ -]?){13,16}\b"),  # card-ish
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # api key
    re.compile(r"AKIA[0-9A-Z]{16}"),  # aws key id
    re.compile(r"[0-9a-fA-F]{32,}"),  # long hex secret
    re.compile(r"(?i)\bpass(word)?\s*[:=]"),  # password=...
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _looks_sensitive(value: str) -> bool:
    """True if the value looks like PII/credentials. TODO(scope): SAP-client-data heuristics."""
    return any(pattern.search(value) for pattern in _SENSITIVE_PATTERNS)


def _is_sensitive(candidate: MemoryCandidate) -> bool:
    return candidate.classification == "sensitive" or _looks_sensitive(candidate.value)


def consider(session: Session, candidate: MemoryCandidate) -> MemoryOutcome:
    """Apply the provenance gate to a memory candidate and return the outcome."""
    if candidate.source_trust != "trusted":
        session.add(
            MemoryCandidateRow(
                source=candidate.source,
                source_trust=candidate.source_trust,
                value_hash=_hash(candidate.value),  # never store untrusted raw value
                classification=candidate.classification,
                status="pending",
            )
        )
        session.commit()
        return "quarantined"

    if _is_sensitive(candidate):
        session.add(
            MemoryCandidateRow(
                source=candidate.source,
                source_trust=candidate.source_trust,
                value_hash=_hash(candidate.value),  # hash only — never the raw sensitive value
                classification="sensitive",
                status="rejected",
            )
        )
        session.commit()
        return "rejected"

    session.add(
        Memory(
            value=candidate.value,
            source=candidate.source,
            source_trust="trusted",
            confidence=1.0,
            may_influence_actions=False,  # must be human-confirmed before it can drive actions
        )
    )
    session.commit()
    return "accepted"
