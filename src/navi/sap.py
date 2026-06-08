"""SAP role-review output contract (build spec §8, §6.6).

The §8 prompt prescribes a fixed markdown shape (Summary / Findings / Gaps / Quick wins). These
helpers grade that *structure* deterministically — used by the goldens now, and available as a
pre-return validator later. Content quality is graded by goldens / LLM-judge, not here.
"""

from __future__ import annotations

REQUIRED_SECTIONS: tuple[str, ...] = (
    "### Summary",
    "### Findings",
    "### Gaps",
    "### Quick wins",
)


def missing_sections(markdown: str) -> list[str]:
    """Return the required §8 section headers absent from the review output (case-insensitive)."""
    low = markdown.lower()
    return [section for section in REQUIRED_SECTIONS if section.lower() not in low]


def has_required_sections(markdown: str) -> bool:
    """True iff the review output contains all four prescribed §8 section headers."""
    return not missing_sections(markdown)
