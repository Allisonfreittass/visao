from functools import lru_cache

from integrations.search.base import SearchProvider
from integrations.search.wikipedia import WikipediaSearch


@lru_cache
def get_search_provider() -> SearchProvider:
    """Override point for tests. Only the fixed Wikipedia API host is ever contacted."""
    return WikipediaSearch()
