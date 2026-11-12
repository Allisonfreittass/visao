from functools import lru_cache

from apps.api.settings import get_settings
from integrations.search.base import SearchProvider
from integrations.search.open_web import ArxivSearch, OpenWebSearch
from integrations.search.tavily import TavilySearch
from integrations.search.wikipedia import WikipediaSearch


@lru_cache
def get_search_provider() -> SearchProvider:
    """Override point for tests. What the conversation searches when it researches something:
    the open web through Tavily when its key is set, with Wikipedia beside it; without the key,
    Wikipedia (pt and en) and arXiv, all public APIs at fixed hosts."""
    key = get_settings().tavily_api_key
    if key:
        return OpenWebSearch([TavilySearch(key.get_secret_value()), WikipediaSearch()])
    return OpenWebSearch([WikipediaSearch(), WikipediaSearch(language="en"), ArxivSearch()])
