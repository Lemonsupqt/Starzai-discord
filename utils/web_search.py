"""
Web search utility for Starzai — provides real-time web and news search
using DuckDuckGo. No API key required.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from duckduckgo_search import AsyncDDGS

from config.constants import (
    WEB_SEARCH_CACHE_TTL,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_MAX_SNIPPET_CHARS,
    WEB_SEARCH_NEWS_MAX_RESULTS,
    WEB_SEARCH_TIMEOUT,
)

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str
    source: str = ""


@dataclass
class SearchResponse:
    """Container for search results with metadata."""

    query: str
    results: List[SearchResult] = field(default_factory=list)
    search_type: str = "web"  # "web" or "news"
    cached: bool = False
    error: Optional[str] = None

    @property
    def has_results(self) -> bool:
        return len(self.results) > 0


class WebSearcher:
    """Async web search client with caching and error handling."""

    def __init__(self) -> None:
        # Simple in-memory cache: {cache_key: (timestamp, SearchResponse)}
        self._cache: Dict[str, Tuple[float, SearchResponse]] = {}

    # ── Cache Management ──────────────────────────────────────────

    def _cache_key(self, query: str, search_type: str) -> str:
        return f"{search_type}:{query.lower().strip()}"

    def _get_cached(self, key: str) -> Optional[SearchResponse]:
        if key in self._cache:
            ts, response = self._cache[key]
            if time.time() - ts < WEB_SEARCH_CACHE_TTL:
                response.cached = True
                return response
            del self._cache[key]
        return None

    def _set_cached(self, key: str, response: SearchResponse) -> None:
        # Evict old entries if cache gets too large
        if len(self._cache) > 200:
            now = time.time()
            expired = [
                k for k, (ts, _) in self._cache.items()
                if now - ts > WEB_SEARCH_CACHE_TTL
            ]
            for k in expired:
                del self._cache[k]

        self._cache[key] = (time.time(), response)

    # ── Web Search ────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        max_results: int = WEB_SEARCH_MAX_RESULTS,
    ) -> SearchResponse:
        """Perform a general web search."""
        cache_key = self._cache_key(query, "web")
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug("Cache hit for web search: %s", query)
            return cached

        try:
            results = await asyncio.wait_for(
                self._do_web_search(query, max_results),
                timeout=WEB_SEARCH_TIMEOUT,
            )
            response = SearchResponse(query=query, results=results, search_type="web")
            self._set_cached(cache_key, response)
            return response
        except asyncio.TimeoutError:
            logger.warning("Web search timed out for: %s", query)
            return SearchResponse(query=query, error="Search timed out. Please try again.")
        except Exception as exc:
            logger.error("Web search error for '%s': %s", query, exc, exc_info=True)
            return SearchResponse(query=query, error=f"Search failed: {exc}")

    async def search_news(
        self,
        query: str,
        max_results: int = WEB_SEARCH_NEWS_MAX_RESULTS,
    ) -> SearchResponse:
        """Search for recent news articles."""
        cache_key = self._cache_key(query, "news")
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug("Cache hit for news search: %s", query)
            return cached

        try:
            results = await asyncio.wait_for(
                self._do_news_search(query, max_results),
                timeout=WEB_SEARCH_TIMEOUT,
            )
            response = SearchResponse(query=query, results=results, search_type="news")
            self._set_cached(cache_key, response)
            return response
        except asyncio.TimeoutError:
            logger.warning("News search timed out for: %s", query)
            return SearchResponse(query=query, error="News search timed out. Please try again.")
        except Exception as exc:
            logger.error("News search error for '%s': %s", query, exc, exc_info=True)
            return SearchResponse(query=query, error=f"News search failed: {exc}")

    # ── Internal Search Methods ───────────────────────────────────

    async def _do_web_search(
        self, query: str, max_results: int
    ) -> List[SearchResult]:
        async with AsyncDDGS() as ddgs:
            raw_results = await ddgs.atext(
                query,
                max_results=max_results,
            )

        results: List[SearchResult] = []
        for r in raw_results or []:
            snippet = r.get("body", "")[:WEB_SEARCH_MAX_SNIPPET_CHARS]
            results.append(
                SearchResult(
                    title=r.get("title", "Untitled"),
                    url=r.get("href", ""),
                    snippet=snippet,
                    source=r.get("source", ""),
                )
            )
        return results

    async def _do_news_search(
        self, query: str, max_results: int
    ) -> List[SearchResult]:
        async with AsyncDDGS() as ddgs:
            raw_results = await ddgs.anews(
                query,
                max_results=max_results,
            )

        results: List[SearchResult] = []
        for r in raw_results or []:
            snippet = r.get("body", "")[:WEB_SEARCH_MAX_SNIPPET_CHARS]
            results.append(
                SearchResult(
                    title=r.get("title", "Untitled"),
                    url=r.get("url", ""),
                    snippet=snippet,
                    source=r.get("source", ""),
                )
            )
        return results

    # ── Formatting Helpers ────────────────────────────────────────

    @staticmethod
    def format_results_for_llm(response: SearchResponse) -> str:
        """Format search results as context for the LLM prompt."""
        if not response.has_results:
            return f"[No search results found for: {response.query}]"

        lines = [
            f'[Web Search Results for "{response.query}" '
            f"— {response.search_type.upper()} search]",
            "",
        ]
        for i, r in enumerate(response.results, 1):
            source_tag = f" ({r.source})" if r.source else ""
            lines.append(f"{i}. **{r.title}**{source_tag}")
            lines.append(f"   URL: {r.url}")
            lines.append(f"   {r.snippet}")
            lines.append("")
        lines.append("[End of search results — synthesize a response using these sources]")
        return "\n".join(lines)

    @staticmethod
    def format_sources_for_embed(
        response: SearchResponse, max_sources: int = 5
    ) -> str:
        """Format source links for display in a Discord embed."""
        if not response.has_results:
            return ""

        lines = []
        for i, r in enumerate(response.results[:max_sources], 1):
            # Truncate title for clean display
            title = r.title[:60] + "…" if len(r.title) > 60 else r.title
            source_tag = f" • {r.source}" if r.source else ""
            lines.append(f"{i}. [{title}]({r.url}){source_tag}")
        return "\n".join(lines)

