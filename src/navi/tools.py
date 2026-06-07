"""The two read-only tools (build spec §6.3).

These callables are **private to the broker** (spec §3): they are underscore-prefixed and
``__all__`` is empty, so no other module imports or calls them — only ``broker.py`` references
them, via the registry it owns. Nothing here mutates the world; both tools are read-only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from navi.config import get_settings

__all__: list[str] = []  # nothing public — the broker is the only caller

logger = logging.getLogger(__name__)

_KB_MAX_RESULTS = 5
_KB_SNIPPET_CHARS = 240
_WEB_TIMEOUT_S = 10.0


# --- arg schemas (spec §6.2 "args validate against the tool's schema") --------------------


class KnowledgeBaseSearchArgs(BaseModel):
    query: str


class WebSearchArgs(BaseModel):
    query: str


# --- knowledge_base_search: keyword search over local markdown (spec §6.3) ----------------
# TODO(scope): upgrade to pgvector semantic RAG; MVP is keyword only.


def _knowledge_base_search(args: KnowledgeBaseSearchArgs) -> dict[str, Any]:
    """Keyword-search the local KB markdown; return top-k {source, snippet}.

    Read-only: opens files for reading only. Missing/empty KB dir returns an empty result set,
    never an error.
    """
    terms = [t for t in args.query.lower().split() if t]
    kb_dir = Path(get_settings().kb_dir)
    hits: list[tuple[int, str, str]] = []  # (score, source, snippet)

    if not kb_dir.is_dir():
        logger.warning("KB dir %s does not exist; returning no results", kb_dir)
        return {"status": "ok", "results": [], "note": f"kb dir '{kb_dir}' not found"}

    for path in sorted(kb_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.exception("Failed to read KB file %s", path)
            continue
        lowered = text.lower()
        score = sum(lowered.count(term) for term in terms)
        if score:
            idx = min((lowered.find(term) for term in terms if term in lowered), default=0)
            start = max(0, idx - 40)
            snippet = text[start : start + _KB_SNIPPET_CHARS].strip().replace("\n", " ")
            hits.append((score, str(path.as_posix()), snippet))

    hits.sort(key=lambda h: h[0], reverse=True)
    results = [{"source": src, "snippet": snip} for _, src, snip in hits[:_KB_MAX_RESULTS]]
    return {"status": "ok", "results": results}


# --- web_search: external API via httpx (spec §6.3) ---------------------------------------
# Default provider: Tavily (https://api.tavily.com/search). TODO(scope): make provider-agnostic.


def _web_search(args: WebSearchArgs) -> dict[str, Any]:
    """Web search via the configured API key.

    If no key is configured, return a clear "unavailable" result rather than crashing (spec
    §6.3) — this is also why tests need no network. Any HTTP/parse failure is caught and
    returned as an "error" result, never raised.
    """
    api_key = get_settings().search_api_key
    if not api_key:
        return {"status": "unavailable", "results": [], "note": "no search_api_key configured"}

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": args.query, "max_results": 5},
            timeout=_WEB_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("web_search request failed")
        return {"status": "error", "results": [], "note": "search request failed"}

    results = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]
    return {"status": "ok", "results": results}
