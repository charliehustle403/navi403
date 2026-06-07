"""Tool tests in isolation (build spec §6.3). Hermetic via ``offline_settings``."""

from __future__ import annotations

from navi.tools import (
    KnowledgeBaseSearchArgs,
    WebSearchArgs,
    _knowledge_base_search,
    _web_search,
)


def test_kb_search_finds_seeded_term(offline_settings: object) -> None:
    result = _knowledge_base_search(KnowledgeBaseSearchArgs(query="vendor"))
    assert result["status"] == "ok"
    assert result["results"], "the temp KB note mentions 'vendor'"
    assert result["results"][0]["source"].endswith(".md")


def test_kb_search_no_match_returns_empty(offline_settings: object) -> None:
    result = _knowledge_base_search(KnowledgeBaseSearchArgs(query="zzz-no-such-term"))
    assert result["status"] == "ok"
    assert result["results"] == []


def test_web_search_unavailable_without_key(offline_settings: object) -> None:
    result = _web_search(WebSearchArgs(query="anything"))
    assert result["status"] == "unavailable"
    assert result["results"] == []
