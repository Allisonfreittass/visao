"""Portuguese Wikipedia via its official API: free, no key, public facts only.

Only the fixed API host is ever contacted (no URL from a page or a model is fetched), redirects
are not followed, and every response is size- and time-bounded. Wikimedia asks API clients to
send a descriptive User-Agent; see https://meta.wikimedia.org/wiki/User-Agent_policy.
"""

import re
import time
from datetime import UTC, datetime

import httpx

from integrations.search.base import SearchError, SearchResult

API_URL = "https://pt.wikipedia.org/w/api.php"
USER_AGENT = (
    "VISAO-research/0.1 (personal research project; https://github.com/Allisonfreittass/visao)"
)
MAX_SNIPPET_CHARS = 700
CACHE_TTL_SECONDS = 3600

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _CONTROL.sub(" ", text)).strip()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class WikipediaSearch:
    name = "wikipedia-pt"

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            timeout=timeout_seconds,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
            transport=transport,
        )
        self._cache: dict[tuple[str, int], tuple[float, list[SearchResult]]] = {}

    def search(self, query: str, max_results: int = 3) -> list[SearchResult]:
        key = (query.strip().lower(), max_results)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

        found = self._get(
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": str(max_results),
                "format": "json",
                "utf8": "1",
            }
        )
        page_ids = [str(hit["pageid"]) for hit in found.get("query", {}).get("search", [])]
        if not page_ids:
            self._cache[key] = (time.monotonic(), [])
            return []

        pages = (
            self._get(
                {
                    "action": "query",
                    "prop": "extracts|info",
                    "exintro": "1",
                    "explaintext": "1",
                    "inprop": "url",
                    "pageids": "|".join(page_ids),
                    "format": "json",
                    "utf8": "1",
                }
            )
            .get("query", {})
            .get("pages", {})
        )

        now = datetime.now(UTC)
        results = []
        for page_id in page_ids:  # keep search ranking order
            page = pages.get(page_id)
            if not page or "missing" in page:
                continue
            url = str(page.get("fullurl", ""))
            if not url.startswith("https://pt.wikipedia.org/"):
                continue
            results.append(
                SearchResult(
                    url=url,
                    title=_clean(str(page.get("title", "")))[:300],
                    snippet=_clean(str(page.get("extract", "")))[:MAX_SNIPPET_CHARS],
                    source="Wikipédia (pt)",
                    retrieved_at=now,
                    updated_at=_parse_time(page.get("touched")),
                )
            )
        self._cache[key] = (time.monotonic(), results)
        return results

    def _get(self, params: dict[str, str]) -> dict:
        try:
            response = self._client.get(API_URL, params=params)
        except httpx.TimeoutException as exc:
            raise SearchError("timeout", "Wikipedia timed out") from exc
        except httpx.HTTPError as exc:
            raise SearchError("network", f"network error: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise SearchError(f"http_{response.status_code}", "Wikipedia returned an error")
        if len(response.content) > 2_000_000:
            raise SearchError("too_large", "response too large")
        try:
            return response.json()
        except ValueError as exc:
            raise SearchError("bad_response", "invalid JSON from Wikipedia") from exc
