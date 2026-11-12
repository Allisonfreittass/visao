"""General web search for the conversation through Tavily (an API made for this: clean snippets,
bounded size). Needs VISION_TAVILY_API_KEY; the free plan has 1000 searches a month. Results are
untrusted text and reach the model only as cited sources."""

from datetime import UTC, datetime

import httpx

from integrations.search.base import SearchError, SearchResult

ENDPOINT = "https://api.tavily.com/search"
MAX_SNIPPET = 900


class TavilySearch:
    name = "tavily"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=10.0)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            response = self._client.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "query": query[:400],
                    "max_results": max(1, min(max_results, 8)),
                    "search_depth": "basic",
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
        except httpx.HTTPError as exc:
            raise SearchError("network", f"Tavily não respondeu: {type(exc).__name__}") from exc
        if response.status_code in (401, 403):
            raise SearchError("auth", "chave do Tavily recusada")
        if response.status_code == 429:
            raise SearchError("rate_limited", "limite do Tavily atingido")
        if response.status_code != 200:
            raise SearchError(f"http_{response.status_code}", "Tavily devolveu um erro")
        try:
            items = response.json().get("results", [])
        except ValueError as exc:
            raise SearchError("bad_response", "resposta inesperada do Tavily") from exc
        now = datetime.now(UTC)
        results = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            url, title = str(item.get("url") or ""), str(item.get("title") or "")
            if not url.startswith("https://") or not title:
                continue
            published = None
            if item.get("published_date"):
                try:
                    published = datetime.fromisoformat(
                        str(item["published_date"]).replace("Z", "+00:00")
                    )
                except ValueError:
                    published = None
            snippet = str(item.get("content") or "")[:MAX_SNIPPET]
            results.append(SearchResult(url, title[:300], snippet, "Web", now, published))
        return results[:max_results]
